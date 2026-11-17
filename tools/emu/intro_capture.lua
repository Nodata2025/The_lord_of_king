-- Captures the opening dialogue window every 30 frames and checks which
-- CHR 1KB banks feed the font slots ($0800-$0FFF) while text is shown.
-- Output directory: $LOK_OUT (absolute path required; Mesen changes its working directory).
local outdir = os.getenv("LOK_OUT") or error("set LOK_OUT")
local f = 0
local log = io.open(outdir .. "/intro_probe.txt", "w")
emu.addEventCallback(function()
  f = f + 1
  if f % 30 == 0 and f <= 1500 then
    local h = io.open(string.format("%s/intro_%05d.png", outdir, f), "wb")
    h:write(emu.takeScreenshot()); h:close()
  end
  if f == 300 or f == 900 then
    local st = emu.getState()
    log:write(string.format("frame %d chrBanks2=%s chrBanks3=%s\n", f,
      tostring(st["mapper.chrBanks2"]), tostring(st["mapper.chrBanks3"])))
  end
  if f >= 1500 then log:close(); emu.stop(0) end
end, emu.eventType.endFrame)
