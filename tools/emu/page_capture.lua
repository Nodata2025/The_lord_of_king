-- State intervention for review captures (NOT normal-play evidence):
-- while the opening cutscene runs, each time the text engine initialises a string
-- ($8031 reads $03D6), the index is swapped for the next one from LOK_TARGETS only while
-- the pointer is fetched ($8031-$803F) and restored at $8042, so the cutscene controller
-- (which polls $03D6) keeps its own sequence.
-- A screenshot is taken 3 frames after every {WAIT} ($80BC) = one per completed page.
-- env: LOK_OUT (absolute dir), LOK_TARGETS ("8,9,10")
local outdir = os.getenv("LOK_OUT") or error("set LOK_OUT")
local targets = {}
for n in string.gmatch(os.getenv("LOK_TARGETS") or "", "%d+") do targets[#targets + 1] = tonumber(n) end
local M = emu.memType.nesMemory
local f, ti, cur, page, pending, saved = 0, 0, -1, 0, nil, nil
local log = io.open(outdir .. "/pages.txt", "a")

emu.addMemoryCallback(function()
  ti = ti + 1
  if targets[ti] then
    saved = emu.read(0x03D6, M)
    emu.write(0x03D6, targets[ti], M)
    cur = targets[ti]
  else
    cur = -1
  end
  page = 0
end, emu.callbackType.exec, 0x8031, 0x8031, emu.cpuType.nes, M)

emu.addMemoryCallback(function()
  if saved then emu.write(0x03D6, saved, M); saved = nil end
end, emu.callbackType.exec, 0x8042, 0x8042, emu.cpuType.nes, M)

emu.addMemoryCallback(function()
  if cur >= 0 then pending = f + 3 end
end, emu.callbackType.exec, 0x80BC, 0x80BC, emu.cpuType.nes, M)

emu.addEventCallback(function()
  f = f + 1
  if pending and f == pending then
    local name = string.format("%s/S%02d_p%02d.png", outdir, cur, page)
    local h = io.open(name, "wb"); h:write(emu.takeScreenshot()); h:close()
    log:write(string.format("S%02d p%02d frame %d bank2=%d\n", cur, page, f, emu.getState()["mapper.chrBanks2"]))
    page = page + 1
    pending = nil
  end
  if (ti > #targets and cur < 0) or f > 12000 then log:close(); emu.stop(0) end
end, emu.eventType.endFrame)
