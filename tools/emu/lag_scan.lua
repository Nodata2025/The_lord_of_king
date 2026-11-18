-- D-39: counts lag frames (main-loop passes spanning more than one NMI) during random play.
-- env ROUND (0-17), LAST (frames). Prints iterations, lag frames and lag per 5 s.
local f=0
local M=emu.memType.nesMemory
local R=tonumber(os.getenv("ROUND"))
local LAST=tonumber(os.getenv("LAST") or "7400")
local nmi=0; local lastn=nil; local iters=0; local lagf=0; local hist={}
emu.addEventCallback(function() nmi=nmi+1 end, emu.eventType.nmi)
emu.addMemoryCallback(function()
  if lastn and f>1400 then
    local d=nmi-lastn
    if d>=1 and d<=4 then iters=iters+1; lagf=lagf+(d-1); local s=f//300; hist[s]=(hist[s] or 0)+(d-1) end
  end
  lastn=nmi
end, emu.callbackType.exec, 0xC74B, 0xC74B, emu.cpuType.nes, M)
emu.addEventCallback(function()
  f=f+1
  if f==690 then emu.write(0xF3,R,M) end
  if f>=LAST then
    local h="" for s=5,LAST//300-1 do h=h..string.format("%4d",hist[s] or 0) end
    io.write(string.format("R%02d iters %d lag %d (%.1f%%) per5s:%s\n",R,iters,lagf,100*lagf/math.max(iters+lagf,1),h))
    emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local i={}
  if (f>=400 and f<406) or (f>=700 and f<706) or (f>=900 and f<1300 and f%60<4) then i.start=true end
  if f>1400 then local r=(f*7919)%100; i.right=(f%240)<170; i.left=(f%240)>=200; i.b=(r<12); i.a=(f%97)<8; i.up=(f%300)<15 end
  emu.setInput(i,0)
end, emu.eventType.inputPolled)
