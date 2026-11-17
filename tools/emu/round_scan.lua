-- State intervention: write round index $F3 (ROUND env, 0-17) on the title screen, skip the
-- opening story with START, then random play; screenshots every 20 frames after 1300 into OUTD.
-- Use with a LOK_KANA=marker build and tools/emu/find_marker.py.
local f=0
local M=emu.memType.nesMemory
local outd=os.getenv("OUTD"); local R=tonumber(os.getenv("ROUND")); local last=tonumber(os.getenv("LAST") or "4000")
local log=io.open(outd.."/log.txt","w")
local seen={}
emu.addMemoryCallback(function()
  local s=emu.read(0x03D6,M)
  log:write(string.format("f%d text string S%02d\n",f,s))
end, emu.callbackType.exec, 0x8031, 0x8031, emu.cpuType.nes, M)
emu.addEventCallback(function()
  f=f+1
  if f==690 then emu.write(0xF3,R,M) end
  if f%20==0 and f>1300 then local h=io.open(string.format("%s/f%05d.png",outd,f),"wb"); h:write(emu.takeScreenshot()); h:close() end
  if f%100==0 then log:write(string.format("f%d F3=%02X F2=%02X\n",f,emu.read(0xF3,M),emu.read(0xF2,M))) end
  if f>=last then log:close(); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local i={}
  if (f>=400 and f<406) or (f>=700 and f<706) or (f>=900 and f<1300 and f%60<4) then i.start=true end
  if f>1400 then local r=(f*7919)%100; i.right=(f%240)<170; i.left=(f%240)>=200; i.b=(r<12); i.a=(f%97)<8; i.up=(f%300)<15 end
  emu.setInput(i,0)
end, emu.eventType.inputPolled)
