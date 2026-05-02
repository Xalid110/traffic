@echo off
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/Xalid110/traffic.git
git push -u origin main
