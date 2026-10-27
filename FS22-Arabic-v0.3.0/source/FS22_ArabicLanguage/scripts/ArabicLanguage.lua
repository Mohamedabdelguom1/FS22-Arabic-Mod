--
-- ArabicLanguage
--
-- Shows the game in Arabic. Mods are loaded when a savegame starts, so this covers
-- everything from then on (HUD, in-game menu, shop, help), not the main menu.
--
--   * replaces texts with the Arabic ones from translations/l10n_ar.xml, or from
--     modSettings/FS22_ArabicLanguage/l10n_ar.xml when present (no repacking needed);
--   * also swaps labels that menus resolved to English before the mod was loaded,
--     by looking the English text up when it is drawn;
--   * wraps the engine's text functions so Arabic is joined, drawn right to left and
--     wrapped line by line (see ArabicShaper);
--   * writes every text of the current game language to
--     modSettings/FS22_ArabicLanguage/l10n_source.xml, the list to translate.
--

ArabicLanguage = {}
ArabicLanguage.MOD_NAME = g_currentModName
ArabicLanguage.MOD_DIR = g_currentModDirectory
ArabicLanguage.SETTINGS_DIR = getUserProfileAppPath() .. "modSettings/FS22_ArabicLanguage/"
ArabicLanguage.TEST_DURATION = 20000    -- ms the confirmation line stays on screen
ArabicLanguage.CACHE_LIMIT = 4000

-- The table the game's own scripts read their globals from. Mod code runs in an
-- environment that falls back to it, and getfenv(0) can be that environment rather
-- than the game's table, so follow the __index chain to the table that really holds
-- the game classes.
local function gameGlobals()
    local candidates = {getfenv(0), _G, getfenv(1)}
    for _, t in ipairs(candidates) do
        local seen = 0
        while type(t) == "table" and seen < 10 do
            if rawget(t, "TextElement") ~= nil and rawget(t, "renderText") ~= nil then
                return t
            end
            local mt = getmetatable(t)
            t = mt ~= nil and mt.__index or nil
            seen = seen + 1
        end
    end
    return getfenv(0)
end

local G = gameGlobals()
local engine = {}           -- the engine functions as they were before the mod
local translations = {}     -- text key -> Arabic
local byEnglish = {}        -- English text (and its upper-case form) -> Arabic
local cache = {}            -- logical text (plus size and width when wrapped) -> visual text
local cacheSize = 0
local state = {wrapWidth = 0, alignment = 0}


-- Inside a mod, g_i18n is a per-mod proxy (with setGlobalText, hasModText...) whose
-- own texts table holds only that mod's texts; the game's instance with all the
-- texts sits behind it as the metatable's __index.
local function gameI18n()
    local i18n = g_i18n
    local mt = getmetatable(i18n)
    while rawget(i18n, "setGlobalText") ~= nil and mt ~= nil and type(mt.__index) == "table" do
        i18n = mt.__index
        mt = getmetatable(i18n)
    end
    return i18n
end


---------------------------------------------------------------- translations

local function loadTranslations(path)
    if not fileExists(path) then
        return 0
    end
    local xml = loadXMLFile("arabicTranslations", path)
    if xml == nil or xml == 0 then
        Logging.warning("ArabicLanguage: cannot read %s", path)
        return 0
    end
    local count, i = 0, 0
    while true do
        local key = string.format("l10n.texts.text(%d)", i)
        local name = getXMLString(xml, key .. "#name")
        if name == nil then
            break
        end
        local text = getXMLString(xml, key .. "#text")
        if text ~= nil and text ~= "" then
            translations[name] = text
            count = count + 1
        end
        i = i + 1
    end
    delete(xml)
    return count
end


-- Log what g_i18n holds, to find where the game keeps its texts.
local function describeI18n(when, i18n)
    local function describe(t, label)
        for k, v in pairs(t) do
            local info = type(v)
            if type(v) == "table" then
                local n, sample = 0, ""
                for kk, vv in pairs(v) do
                    n = n + 1
                    if n <= 3 then
                        sample = sample .. string.format(" [%s]=%s:%s", tostring(kk), type(vv), tostring(vv):sub(1, 40))
                    end
                end
                info = string.format("table with %d entries%s", n, sample)
            elseif type(v) ~= "function" then
                info = info .. " " .. tostring(v):sub(1, 60)
            end
            print(string.format("ArabicLanguage:   %s.%s = %s", label, tostring(k), info))
        end
    end
    print("ArabicLanguage: g_i18n contents " .. when)
    describe(i18n, "g_i18n")
    local mt = getmetatable(i18n)
    if mt ~= nil and type(mt.__index) == "table" then
        describe(mt.__index, "class")
    end
end


local function exportSourceTexts(texts)
    local keys = {}
    for name, text in pairs(texts) do
        if type(text) == "string" then
            keys[#keys + 1] = name
        end
    end
    table.sort(keys)
    if #keys == 0 then
        Logging.warning("ArabicLanguage: g_i18n.texts holds no texts, nothing exported")
        describeI18n("at map load", gameI18n())
        return
    end

    createFolder(getUserProfileAppPath() .. "modSettings/")
    createFolder(ArabicLanguage.SETTINGS_DIR)
    local path = ArabicLanguage.SETTINGS_DIR .. "l10n_source.xml"
    local xml = createXMLFile("arabicSource", path, "l10n")
    setXMLString(xml, "l10n#language", tostring(g_languageShort))
    for i, name in ipairs(keys) do
        local key = string.format("l10n.texts.text(%d)", i - 1)
        setXMLString(xml, key .. "#name", name)
        setXMLString(xml, key .. "#text", texts[name])
        if translations[name] ~= nil then
            setXMLString(xml, key .. "#ar", translations[name])
        end
    end
    saveXMLFile(xml)
    delete(xml)
    print(string.format("ArabicLanguage: exported %d texts to %s", #keys, path))
end


local function applyTranslations(i18n)
    local texts = i18n.texts
    if type(texts) == "table" then
        for name, arabic in pairs(translations) do
            local english = texts[name]
            if type(english) == "string" and english ~= "" then
                byEnglish[english] = arabic
                byEnglish[utf8ToUpper(english)] = arabic
            end
            texts[name] = arabic
        end
    end

    -- texts requested from now on, including mod texts with the same key
    local getText = i18n.getText
    i18n.getText = function(self, name, customEnv)
        local arabic = translations[name]
        if arabic ~= nil then
            return arabic
        end
        return getText(self, name, customEnv)
    end
end


---------------------------------------------------------------- drawing

local function remember(text, visual)
    if cacheSize >= ArabicLanguage.CACHE_LIMIT then
        cache, cacheSize = {}, 0
    end
    cache[text] = visual
    cacheSize = cacheSize + 1
    return visual
end


-- Arabic for a label that was resolved to English before the mod loaded
local function translate(text)
    return byEnglish[text] or text
end


-- Visual text for one call. Returns the text unchanged when it has no Arabic.
local function prepare(size, text)
    text = translate(text)
    if not ArabicShaper.hasArabic(text) then
        return text, false
    end
    if state.wrapWidth > 0 then
        local key = string.format("%s\0%.5f\0%.5f", text, size, state.wrapWidth)
        local visual = cache[key]
        if visual == nil then
            local measure = function(s) return engine.getTextWidth(size, s) end
            engine.setTextWrapWidth(0)
            visual = remember(key, ArabicShaper.wrap(text, state.wrapWidth, measure))
            engine.setTextWrapWidth(state.wrapWidth)
        end
        return visual, true
    end
    return cache[text] or remember(text, ArabicShaper.toVisual(text)), true
end


-- Run fn with the engine's wrapping off: the text is already broken into lines.
local function unwrapped(fn, ...)
    if state.wrapWidth > 0 then
        engine.setTextWrapWidth(0)
        local a, b = fn(...)
        engine.setTextWrapWidth(state.wrapWidth)
        return a, b
    end
    return fn(...)
end


local function hookTextFunctions()
    for _, name in ipairs({"renderText", "getTextWidth", "getTextHeight", "setTextWrapWidth", "setTextAlignment"}) do
        engine[name] = G[name]
    end
    state.alignment = RenderText.ALIGN_LEFT

    G.setTextWrapWidth = function(width)
        state.wrapWidth = width or 0
        engine.setTextWrapWidth(width)
    end

    G.setTextAlignment = function(alignment)
        state.alignment = alignment
        engine.setTextAlignment(alignment)
    end

    G.renderText = function(x, y, size, text)
        if type(text) ~= "string" then
            return engine.renderText(x, y, size, text)
        end
        local visual, rtl = prepare(size, text)
        if not rtl then
            return engine.renderText(x, y, size, visual)
        end
        if state.wrapWidth > 0 and state.alignment == RenderText.ALIGN_LEFT then
            -- a wrapped Arabic paragraph reads from the right edge of its box
            local width = state.wrapWidth
            engine.setTextAlignment(RenderText.ALIGN_RIGHT)
            unwrapped(engine.renderText, x + width, y, size, visual)
            engine.setTextAlignment(state.alignment)
            return
        end
        unwrapped(engine.renderText, x, y, size, visual)
    end

    G.getTextWidth = function(size, text)
        if type(text) ~= "string" then
            return engine.getTextWidth(size, text)
        end
        local visual, rtl = prepare(size, text)
        if not rtl then
            return engine.getTextWidth(size, visual)
        end
        return unwrapped(engine.getTextWidth, size, visual)
    end

    G.getTextHeight = function(size, text)
        if type(text) ~= "string" then
            return engine.getTextHeight(size, text)
        end
        local visual, rtl = prepare(size, text)
        if not rtl then
            return engine.getTextHeight(size, visual)
        end
        return unwrapped(engine.getTextHeight, size, visual)
    end
end


---------------------------------------------------------------- mod events

function ArabicLanguage:loadMap(name)
    self.testTime = ArabicLanguage.TEST_DURATION
    -- the texts as the game had them, before Arabic replaced them in init()
    if self.sourceTexts ~= nil then
        exportSourceTexts(self.sourceTexts)
        self.sourceTexts = nil
    else
        Logging.warning("ArabicLanguage: g_i18n.texts is not available, nothing exported")
        describeI18n("at map load", gameI18n())
    end
end


function ArabicLanguage:update(dt)
    if self.testTime ~= nil then
        self.testTime = self.testTime - dt
        if self.testTime <= 0 then
            self.testTime = nil
        end
    end
end


function ArabicLanguage:draw()
    if self.testTime ~= nil then
        setTextAlignment(RenderText.ALIGN_CENTER)
        setTextBold(true)
        setTextColor(1, 1, 1, 1)
        renderText(0.5, 0.93, 0.022, string.format("مود التعريب يعمل — %d نصاً مترجماً", self.count))
        setTextBold(false)
        setTextAlignment(RenderText.ALIGN_LEFT)
    end
end


function ArabicLanguage:init()
    -- the user's file comes second so its entries win
    loadTranslations(ArabicLanguage.MOD_DIR .. "translations/l10n_ar.xml")
    loadTranslations(ArabicLanguage.SETTINGS_DIR .. "l10n_ar.xml")
    self.count = 0
    for _ in pairs(translations) do
        self.count = self.count + 1
    end

    local i18n = gameI18n()
    local gameCount = 0
    if type(i18n.texts) == "table" then
        local copy = {}
        for name, text in pairs(i18n.texts) do
            copy[name] = text
            gameCount = gameCount + 1
        end
        self.sourceTexts = copy
    end

    applyTranslations(i18n)
    hookTextFunctions()
    print(string.format("ArabicLanguage: text functions wrapped in the game's globals (getfenv(0) was %s)",
        G == getfenv(0) and "the game's table" or "the mod environment"))
    addModEventListener(self)
    print(string.format("ArabicLanguage: %d Arabic texts loaded, game has %d texts (language: %s)",
        self.count, gameCount, tostring(g_languageShort)))
end


ArabicLanguage:init()
