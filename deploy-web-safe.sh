#!/bin/zsh
set -e

echo "[1/5] Building web app..."

echo "[2/5] Publishing index & vite.svg..."

echo "[3/5] Publishing assets (with --delete)..."

echo "[4/5] Committing changes..."

echo "[5/5] Pushing to origin/main..."


cd ~/cogmyra-web
npm run build

cp -f ~/cogmyra-web/dist/index.html  ~/cogmyra-dev/docs/index.htmlcp -f ~/cogmyra-web/dist/vite.svg    ~/cogmyra-dev/docs/vite.svg
rsync -av --delete ~/cogmyra-web/dist/assets/ ~/cogmyra-dev/docs/assets/

cd ~/cogmyra-dev
git add docs/index.html docs/robots.txt docs/vite.svg docs/assets
git commit -m "deploy(web): update landing build; keep policies/guide intact"
git push origin main
echo "✅ Deploy complete! Visit https://cogmyra.github.io/"
