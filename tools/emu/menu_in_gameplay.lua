-- State intervention: after reaching stage 1 gameplay, call the item menu ($CA4B) from the
-- main loop's frame wait (E378 from $C74E), pick a weapon, then keep playing.
-- env TAG selects output names under /home/claude/emu (adjust paths for your machine).
local f, done, back = 0, false, nil
local M = emu.memType.nesMemory
local tag = os.getenv("TAG")
local out = io.open("/home/claude/emu/gm_"..tag..".txt","w")
local function shot(n) local h=io.open(string.format("/home/claude/emu/gm_%s_%s.png",tag,n),"wb"); h:write(emu.takeScreenshot()); h:close() end
emu.addMemoryCallback(function()
  if f >= 1500 and not done then
    done = true
    local st = emu.getState(); local pc, sp = st["cpu.pc"], st["cpu.sp"]
    local ret = pc - 1
    emu.write(0x100 + sp, (ret >> 8) & 0xFF, M); emu.write(0x100 + ((sp - 1) & 0xFF), ret & 0xFF, M)
    emu.setState({["cpu.sp"] = (sp - 2) & 0xFF, ["cpu.pc"] = 0xCA4B})
    local lo=emu.read(0x100+((sp+1)&0xFF),M); local hi=emu.read(0x100+((sp+2)&0xFF),M)
    out:write(string.format("inject f%d (E378 called from %04X) bank8000=%s\n", f, hi*256+lo+1, tostring(st["mapper.prgBanks0"])))
  end
end, emu.callbackType.exec, 0xE378, 0xE378, emu.cpuType.nes, M)
-- detect the return from $CA4B: exec of the instruction after our fake return = E378 entry again with done
emu.addEventCallback(function()
  f = f + 1
  if f == 1495 then shot("0_before") end
  if f % 20 == 0 then out:write(string.format("f%d menu=%02X $03=%02X chr2=%d\n", f, emu.read(0x556,M), emu.read(3,M), emu.getState()["mapper.chrBanks2"])) end
  if f == 2040 then shot("1_menu") end
  if f == 2600 or f == 2700 or f == 2800 or f == 3000 or f == 3400 then shot("2_after_"..f) end
  if f >= 3400 then out:close(); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local i = {}
  if f % 150 < 6 and f > 200 and f < 800 then i.start = true end
  if f > 1700 and f < 1706 then i.down = true end
  if f > 1900 and f < 1906 then i.right = true end
  if f > 2000 and f < 2006 then i.a = true end
  if f > 2900 then i.right = (f % 120) < 90; i.b = (f % 30) < 4 end
  emu.setInput(i, 0)
end, emu.eventType.inputPolled)
