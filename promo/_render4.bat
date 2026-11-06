@echo off
cd /d "C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo"
echo === BGM start %TIME% === > out\r4.log
call node_modules\.bin\remotion.cmd render src/index.tsx PotPromo out/pot-promo.mp4 >> out\r4.log 2>&1
echo BGM exit=%ERRORLEVEL% %TIME% >> out\r4.log
call node_modules\.bin\remotion.cmd render src/index.tsx PotPromo out/pot-promo-nobgm.mp4 --props=props-nobgm.json >> out\r4.log 2>&1
echo NOBGM exit=%ERRORLEVEL% %TIME% >> out\r4.log
echo === ALL DONE %TIME% === >> out\r4.log
