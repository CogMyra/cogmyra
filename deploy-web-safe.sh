#!/bin/zsh
set -e

echo "[1/5] Building web app..."
cd ~/cogmyra-web
npm run build

echo "[2/5] Publishing vite.svg (leave docs/index.html alone)..."
cp -f ~/cogmyra-web/dist/vite.svg    ~/cogmyra-dev/docs/vite.svg   || true

echo "[3/5] Publishing assets (with --delete if present)..."
if [ -d ~/cogmyra-web/dist/assets ]; then
  rsync -av --delete ~/cogmyra-web/dist/assets/ ~/cogmyra-dev/docs/assets/
else
  echo "   (no dist/assets folder — skipping)"
fi

echo "[4/5] Committing changes..."
cd ~/cogmyra-dev
git add docs/index.html docs/vite.svg docs/assets || true
git commit -m "deploy(web): publish latest index (+assets if any)" || true

echo "[5/5] Pushing to origin/main..."
git push origin main || true

echo "✅ Deploy complete! Visit https://cogmyra.com/"
