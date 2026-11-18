-- D-40: sprite overflow per frame during random play (EASY, HP kept full). env ROUND, N.
-- Prints frames where a player sprite fell beyond the 8th on its line, sprites per frame,
-- dropped sprite-lines and overflowing lines per frame (8x16 sprites).
local f=0
local M=emu.memType.nesMemory
local loaded=false
local p0,p1=nil,nil; local pdrop=0; local pframes=0
emu.addMemoryCallback(function() p0=emu.read(0x46,emu.memType.nesMemory) end, emu.callbackType.exec, 0xD890, 0xD890, emu.cpuType.nes, emu.memType.nesMemory)
for _,ra in ipairs({0xCFC4,0xCFC9,0xC760}) do emu.addMemoryCallback(function() if p0 and not p1 then p1=emu.read(0x46,emu.memType.nesMemory) end end, emu.callbackType.exec, ra, ra, emu.cpuType.nes, emu.memType.nesMemory) end
local frames=0; local drop=0; local blank=0; local spr=0; local blankdrop=0; local ovflines=0
emu.addMemoryCallback(function()
  if not loaded and f>=1500 and emu.read(0xF8,M)==3 then loaded=true end
end, emu.callbackType.exec, 0xE0D7, 0xE0D7, emu.cpuType.nes, M)
local function chrblank(tile)
  local addr=(tile&1)*0x1000+(tile&0xFE)*16
  local k=addr//1024
  local bank=(emu.read(0x140+2*k,M)&0x0F)|((emu.read(0x141+2*k,M)&0x0F)<<4)
  local base=bank*1024+(addr%1024)
  for i=0,31 do if emu.read(base+i,emu.memType.nesChrRom)~=0 then return false end end
  return true
end
emu.addEventCallback(function()
  f=f+1
  if f==690 then emu.write(0xF3,tonumber(os.getenv("ROUND")),M) emu.write(0x11E,0,M) emu.write(0x11F,0x5A,M) end if loaded then emu.write(0x91,20,M) end
  if loaded then
    frames=frames+1
    local lines={}
    for s=0,63 do
      local y=emu.read(0x200+4*s,M)
      if y<0xEF then
        spr=spr+1
        local b=chrblank(emu.read(0x201+4*s,M)) -- 8x8 sprites assumed
        if b then blank=blank+1 end
        for l=y+1,y+16 do lines[l]=(lines[l] or 0)+1 if lines[l]>8 then drop=drop+1 if b then blankdrop=blankdrop+1 end end end
      end
    end
    for l,c in pairs(lines) do if c>8 then ovflines=ovflines+1 end end
    -- player sprites dropped: count lines where a player sprite is beyond the 8th
    if p0 and p1 then
      local cnt={} local pd=false
      for s2=0,63 do local y=emu.read(0x200+4*s2,M) if y<0xEF then for l=y+1,y+16 do cnt[l]=(cnt[l] or 0)+1 if cnt[l]>8 and s2>=p0 and s2<p1 then pd=true end end end end
      if pd then pdrop=pdrop+1 end
    end
    p0=nil p1=nil
  end
  if f==1500+tonumber(os.getenv("N")) then io.write("R"..os.getenv("ROUND").." ") io.write(string.format("player-dropped frames %d ",pdrop)) io.write(string.format("frames %d sprites/frame %.1f blank/frame %.1f dropped-lines/frame %.1f overflow-lines/frame %.1f\n",frames,spr/frames,blank/frames,drop/frames,ovflines/frames)) emu.stop(0) end
end, emu.eventType.endFrame)
emu.addEventCallback(function()
  local i={}
  if (f>=400 and f<406) or (f>=700 and f<706) or (f>=900 and f<1300 and f%60<4) then i.start=true end
  if f>1400 then local r=(f*7919)%100; i.right=(f%240)<170; i.left=(f%240)>=200; i.b=(r<12); i.a=(f%97)<8; i.up=(f%300)<15 end
  emu.setInput(i,0)
end, emu.eventType.inputPolled)
