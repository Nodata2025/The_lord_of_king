-- State intervention: lives $96 := 0 at frame 1500, random play until game over, then
-- START/DOWN on the following screens. Screenshots every 10 frames from 5000 into OUTD.
local f=0
local M=emu.memType.nesMemory
local outd=os.getenv("OUTD")
emu.addEventCallback(function()
  f=f+1
  if f==1500 then emu.write(0x96,0,M) end
  if f>=5000 and f%10==0 then local h=io.open(string.format("%s/f%05d.png",outd,f),"wb"); h:write(emu.takeScreenshot()); h:close() end
  if f>=9000 then emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local i={}
  if f%150<6 and f>200 and f<800 then i.start=true end
  if f>900 and f<7000 then
    local r=(f*7919)%100
    i.right=(f%240)<170; i.left=(f%240)>=200; i.b=(r<12); i.a=(f%97)<8
  end
  if f>7000 and f%200<5 then i.start=true end
  if f>7000 and f%200>=100 and f%200<105 then i.down=true end
  emu.setInput(i,0)
end, emu.eventType.inputPolled)
