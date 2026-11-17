-- D-17 check: DIFF=0/1/2 sets the difficulty before the title menu, then plays round 1 and logs
-- HP changes, knockback X (hurt start/end) and the PW gauge to /home/claude/emu/dt_<DIFF>.txt.
local f=0
local M=emu.memType.nesMemory
local D=tonumber(os.getenv("DIFF"))
local out=io.open("/home/claude/emu/dt_"..D..".txt","w")
local php=-1; local hurt=-1
emu.addEventCallback(function()
  f=f+1
  if f==690 then emu.write(0x11E,D,M); emu.write(0x11F,D ~ 0x5A,M) end
  local hp=emu.read(0x91,M)
  if hp~=php then out:write(string.format("f%d hp %d lives %02X\n",f,hp,emu.read(0x96,M))); php=hp end
  local h=emu.read(0x76,M)
  if (h & 0x20)~=0 and hurt<0 then hurt=f; out:write(string.format("f%d hurt start x=%d\n",f,emu.read(0x6D,M)+256*emu.read(0x6E,M))) end
  if (h & 0x20)==0 and hurt>=0 then out:write(string.format("f%d hurt end x=%d\n",f,emu.read(0x6D,M)+256*emu.read(0x6E,M))); hurt=-1 end
  if f%500==0 then out:write(string.format("f%d pw %d/%d.%d\n",f,emu.read(0x8E,M),emu.read(0x89,M),emu.read(0x8D,M))) end
  if f>=6000 then out:close(); emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local i={}
  if (f>=400 and f<406) or (f>=700 and f<706) or (f>=760 and f<766) or (f>=900 and f<906) then i.start=true end
  if f>1100 then i.right=(f%300)<250; i.left=(f%300)>=270; if f%50<3 then i.a=true end; if f%37<2 then i.b=true end end
  emu.setInput(i,0)
end, emu.eventType.inputPolled)
