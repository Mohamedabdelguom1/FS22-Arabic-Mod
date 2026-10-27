--
-- ArabicShaper
--
-- The game's text renderer draws characters strictly left to right, one glyph per
-- codepoint, without joining letters. This turns a logical Arabic string into the
-- string to draw: each letter replaced by its joined presentation form (the font
-- carries them since add_arabic_glyphs.py), and each line put in visual order,
-- with Latin words and numbers kept left to right inside it.
--
-- Pure Lua 5.1, no engine functions, so it can be tested outside the game.
--

ArabicShaper = {}

-- base letter -> {isolated, final, initial, medial}; nil where the letter has no such form
local FORMS = {
    [0x0621] = {0xFE80, nil, nil, nil},          -- hamza
    [0x0622] = {0xFE81, 0xFE82, nil, nil},       -- alef with madda
    [0x0623] = {0xFE83, 0xFE84, nil, nil},       -- alef with hamza above
    [0x0624] = {0xFE85, 0xFE86, nil, nil},       -- waw with hamza
    [0x0625] = {0xFE87, 0xFE88, nil, nil},       -- alef with hamza below
    [0x0626] = {0xFE89, 0xFE8A, 0xFE8B, 0xFE8C}, -- yeh with hamza
    [0x0627] = {0xFE8D, 0xFE8E, nil, nil},       -- alef
    [0x0628] = {0xFE8F, 0xFE90, 0xFE91, 0xFE92}, -- beh
    [0x0629] = {0xFE93, 0xFE94, nil, nil},       -- teh marbuta
    [0x062A] = {0xFE95, 0xFE96, 0xFE97, 0xFE98}, -- teh
    [0x062B] = {0xFE99, 0xFE9A, 0xFE9B, 0xFE9C}, -- theh
    [0x062C] = {0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0}, -- jeem
    [0x062D] = {0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4}, -- hah
    [0x062E] = {0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8}, -- khah
    [0x062F] = {0xFEA9, 0xFEAA, nil, nil},       -- dal
    [0x0630] = {0xFEAB, 0xFEAC, nil, nil},       -- thal
    [0x0631] = {0xFEAD, 0xFEAE, nil, nil},       -- reh
    [0x0632] = {0xFEAF, 0xFEB0, nil, nil},       -- zain
    [0x0633] = {0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4}, -- seen
    [0x0634] = {0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8}, -- sheen
    [0x0635] = {0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC}, -- sad
    [0x0636] = {0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0}, -- dad
    [0x0637] = {0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4}, -- tah
    [0x0638] = {0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8}, -- zah
    [0x0639] = {0xFEC9, 0xFECA, 0xFECB, 0xFECC}, -- ain
    [0x063A] = {0xFECD, 0xFECE, 0xFECF, 0xFED0}, -- ghain
    [0x0641] = {0xFED1, 0xFED2, 0xFED3, 0xFED4}, -- feh
    [0x0642] = {0xFED5, 0xFED6, 0xFED7, 0xFED8}, -- qaf
    [0x0643] = {0xFED9, 0xFEDA, 0xFEDB, 0xFEDC}, -- kaf
    [0x0644] = {0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0}, -- lam
    [0x0645] = {0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4}, -- meem
    [0x0646] = {0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8}, -- noon
    [0x0647] = {0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC}, -- heh
    [0x0648] = {0xFEED, 0xFEEE, nil, nil},       -- waw
    [0x0649] = {0xFEEF, 0xFEF0, nil, nil},       -- alef maksura (joins on the right only in Arabic)
    [0x064A] = {0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4}, -- yeh
    [0x067E] = {0xFB56, 0xFB57, 0xFB58, 0xFB59}, -- peh
    [0x0686] = {0xFB7A, 0xFB7B, 0xFB7C, 0xFB7D}, -- tcheh
    [0x0698] = {0xFB8A, 0xFB8B, nil, nil},       -- jeh
    [0x06A9] = {0xFB8E, 0xFB8F, 0xFB90, 0xFB91}, -- keheh
    [0x06AF] = {0xFB92, 0xFB93, 0xFB94, 0xFB95}, -- gaf
    [0x06CC] = {0xFBFC, 0xFBFD, 0xFBFE, 0xFBFF}, -- farsi yeh
}

-- lam followed by one of these alefs becomes a single ligature: {isolated, final}
local LAM_ALEF = {
    [0x0622] = {0xFEF5, 0xFEF6},
    [0x0623] = {0xFEF7, 0xFEF8},
    [0x0625] = {0xFEF9, 0xFEFA},
    [0x0627] = {0xFEFB, 0xFEFC},
}

local TATWEEL = 0x0640
local LAM = 0x0644

local MIRROR = {
    [0x28] = 0x29, [0x29] = 0x28, [0x5B] = 0x5D, [0x5D] = 0x5B, [0x7B] = 0x7D, [0x7D] = 0x7B,
    [0x3C] = 0x3E, [0x3E] = 0x3C, [0xAB] = 0xBB, [0xBB] = 0xAB,
}

-- characters that stick to an adjacent number: "25%", "€ 100", "-5"
local NUMBER_AFFIX = {
    [0x25] = true, [0x24] = true, [0x23] = true, [0x2B] = true, [0x2D] = true,
    [0xB0] = true, [0x20AC] = true, [0xA3] = true, [0x066A] = true,
}

-- characters that stay inside a number when they sit between two digits: "1,250.5", "12:30"
local NUMBER_SEPARATOR = {[0x2C] = true, [0x2E] = true, [0x3A] = true, [0x2F] = true, [0x066B] = true, [0x066C] = true}


---------------------------------------------------------------- UTF-8

function ArabicShaper.decode(s)
    local cps, i, n = {}, 1, #s
    while i <= n do
        local c = s:byte(i)
        if c < 0x80 then
            cps[#cps + 1] = c
            i = i + 1
        elseif c < 0xE0 then
            cps[#cps + 1] = (c % 0x20) * 0x40 + (s:byte(i + 1) or 0x80) % 0x40
            i = i + 2
        elseif c < 0xF0 then
            cps[#cps + 1] = (c % 0x10) * 0x1000 + ((s:byte(i + 1) or 0x80) % 0x40) * 0x40
                + (s:byte(i + 2) or 0x80) % 0x40
            i = i + 3
        else
            cps[#cps + 1] = (c % 0x08) * 0x40000 + ((s:byte(i + 1) or 0x80) % 0x40) * 0x1000
                + ((s:byte(i + 2) or 0x80) % 0x40) * 0x40 + (s:byte(i + 3) or 0x80) % 0x40
            i = i + 4
        end
    end
    return cps
end


local char = string.char
local floor = math.floor

local function encodeOne(cp)
    if cp < 0x80 then
        return char(cp)
    elseif cp < 0x800 then
        return char(0xC0 + floor(cp / 0x40), 0x80 + cp % 0x40)
    elseif cp < 0x10000 then
        return char(0xE0 + floor(cp / 0x1000), 0x80 + floor(cp / 0x40) % 0x40, 0x80 + cp % 0x40)
    end
    return char(0xF0 + floor(cp / 0x40000), 0x80 + floor(cp / 0x1000) % 0x40,
        0x80 + floor(cp / 0x40) % 0x40, 0x80 + cp % 0x40)
end


function ArabicShaper.encode(cps, first, last)
    local parts = {}
    for i = first or 1, last or #cps do
        parts[#parts + 1] = encodeOne(cps[i])
    end
    return table.concat(parts)
end


---------------------------------------------------------------- classification

-- Arabic script in its logical form (U+0600..06FF), as typed in translations;
-- lead bytes 0xD8..0xDB in UTF-8
function ArabicShaper.hasArabic(s)
    return s:find("[\216-\219][\128-\191]") ~= nil
end


local function isRtl(cp)
    return (cp >= 0x0590 and cp <= 0x08FF) or (cp >= 0xFB1D and cp <= 0xFDFF) or (cp >= 0xFE70 and cp <= 0xFEFF)
end


local function isDigit(cp)
    return (cp >= 0x30 and cp <= 0x39) or (cp >= 0x0660 and cp <= 0x0669) or (cp >= 0x06F0 and cp <= 0x06F9)
end


local function isLtr(cp)
    if cp < 0x80 then
        return (cp >= 0x41 and cp <= 0x5A) or (cp >= 0x61 and cp <= 0x7A)
    end
    if cp < 0xC0 or cp == 0xD7 or cp == 0xF7 then
        return false
    end
    if cp >= 0x2000 and cp <= 0x2BFF then  -- punctuation, currency and symbols
        return false
    end
    if cp >= 0xFE00 and cp <= 0xFE6F then
        return false
    end
    return not isRtl(cp)
end


local function isMark(cp)
    return (cp >= 0x064B and cp <= 0x065F) or cp == 0x0670
end


---------------------------------------------------------------- joining

local function joinsNext(cp)
    if cp == TATWEEL then
        return true
    end
    local f = FORMS[cp]
    return f ~= nil and f[3] ~= nil
end


local function joinsPrevious(cp)
    if cp == TATWEEL then
        return true
    end
    local f = FORMS[cp]
    return f ~= nil and f[2] ~= nil
end


-- Replace letters by their joined forms. Harakat are dropped: the renderer cannot
-- stack them over the letter.
local function shape(cps)
    local letters = {}
    for _, cp in ipairs(cps) do
        if not isMark(cp) then
            letters[#letters + 1] = cp
        end
    end

    local out, i, n = {}, 1, #letters
    while i <= n do
        local cp = letters[i]
        local prev = letters[i - 1]
        local afterJoining = prev ~= nil and joinsNext(prev)
        local lig = cp == LAM and LAM_ALEF[letters[i + 1]]
        if lig then
            out[#out + 1] = afterJoining and lig[2] or lig[1]
            i = i + 2
        else
            local f = FORMS[cp]
            if f == nil then
                out[#out + 1] = cp
            else
                local nxt = letters[i + 1]
                local left = f[3] ~= nil and nxt ~= nil and joinsPrevious(nxt)
                local right = afterJoining and f[2] ~= nil
                local form
                if right and left then
                    form = f[4]
                elseif right then
                    form = f[2]
                elseif left then
                    form = f[3]
                end
                out[#out + 1] = form or f[1]
            end
            i = i + 1
        end
    end
    return out
end


---------------------------------------------------------------- ordering

-- Direction of each character: true for left to right. Latin letters are strong
-- LTR, Arabic strong RTL, digits form LTR runs but count as RTL for their
-- neighbours unless they follow Latin text ("Simulator 22"). Spaces and
-- punctuation take the direction of their surroundings, RTL when in doubt.
local function directions(cps)
    local n = #cps
    local kind = {}
    for i = 1, n do
        local cp = cps[i]
        kind[i] = (isRtl(cp) and not isDigit(cp) and "R") or (isDigit(cp) and "N") or (isLtr(cp) and "L") or false
    end
    -- separators between digits and affixes next to numbers belong to the number
    for i = 1, n do
        local cp = cps[i]
        if not kind[i] then
            if NUMBER_SEPARATOR[cp] and kind[i - 1] == "N" and kind[i + 1] == "N" then
                kind[i] = "N"
            end
        end
    end
    for i = 1, n do
        if not kind[i] and NUMBER_AFFIX[cps[i]] then
            if kind[i - 1] == "N" or kind[i + 1] == "N" then
                kind[i] = "N"
            end
        end
    end
    -- numbers after Latin text are part of it
    local last = "R"
    for i = 1, n do
        if kind[i] == "N" and last == "L" then
            kind[i] = "L"
        elseif kind[i] == "L" or kind[i] == "R" then
            last = kind[i]
        end
    end
    -- neutrals are LTR only between two LTR
    local ltr = {}
    local before = "R"
    for i = 1, n do
        local k = kind[i]
        if k then
            ltr[i] = k ~= "R"
            if k == "L" or k == "R" then
                before = k
            elseif k == "N" then
                before = "R"
            end
        else
            local after = "R"
            for j = i + 1, n do
                local kj = kind[j]
                if kj then
                    after = kj == "L" and "L" or "R"
                    break
                end
            end
            ltr[i] = before == "L" and after == "L"
        end
    end
    return ltr
end


-- one line (no newlines), already shaped, into visual order
local function reorder(cps)
    local n = #cps
    if n == 0 then
        return cps
    end
    local ltr = directions(cps)
    local out = {}
    -- walk the runs from the end of the line to its start
    local i = n
    while i >= 1 do
        local j = i
        while j > 1 and ltr[j - 1] == ltr[i] do
            j = j - 1
        end
        if ltr[i] then
            for k = j, i do
                out[#out + 1] = cps[k]
            end
        else
            for k = i, j, -1 do
                local cp = cps[k]
                out[#out + 1] = MIRROR[cp] or cp
            end
        end
        i = j - 1
    end
    return out
end


-- Visual form of one logical line.
function ArabicShaper.visualLine(line)
    return ArabicShaper.encode(reorder(shape(ArabicShaper.decode(line))))
end


-- Visual form of a text that may contain newlines; each line keeps its place.
function ArabicShaper.toVisual(text)
    if not ArabicShaper.hasArabic(text) then
        return text
    end
    local lines = {}
    for line in (text .. "\n"):gmatch("(.-)\n") do
        lines[#lines + 1] = ArabicShaper.visualLine(line)
    end
    return table.concat(lines, "\n")
end


-- Break a logical text into lines no wider than maxWidth, measuring the visual
-- form with measure(visualString). The engine cannot wrap reordered text itself:
-- it would put the end of the sentence on the first line. Returns the visual text.
function ArabicShaper.wrap(text, maxWidth, measure)
    local out = {}
    for paragraph in (text .. "\n"):gmatch("(.-)\n") do
        local line = nil
        for word in paragraph:gmatch("%S+") do
            local candidate = line and (line .. " " .. word) or word
            if line ~= nil and measure(ArabicShaper.visualLine(candidate)) > maxWidth then
                out[#out + 1] = ArabicShaper.visualLine(line)
                line = word
            else
                line = candidate
            end
        end
        out[#out + 1] = ArabicShaper.visualLine(line or "")
    end
    return table.concat(out, "\n")
end
