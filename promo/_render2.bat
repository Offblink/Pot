@echo off
cd /d "C:\Users\37549\Desktop\Vibe Coding\useful\Pot\promo"
echo === BGM start %TIME% === > out\r2.log
call node_modules\.bin\remotion.cmd render src/index.ts PotPromo out/pot-promo.mp4 >> out\r2.log 2>&1
echo BGM exit=%ERRORLEVEL% %TIME% >> out\r2.log
call node_modules\.bin\remotion.cmd render src/index.ts PotPromo out/pot-promo-nobgm.mp4 --props=props-nobgm.json >> out\r2.log 2>&1
echo NOBGM exit=%ERRORLEVEL% %TIME% >> out\r2.log
echo === ALL DONE %TIME% === >> out\r2.log
