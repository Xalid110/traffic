import os
# Add files
os.system('git add .')
# Commit
os.system('git commit -m "Initial commit"')
# Ensure we are on main
os.system('git branch -M main')
# Try to push
os.system('git push -u origin main')
