#!/bin/zsh
set -e

echo "[1/5] Building web app..."

echo "[2/5] Publishing index/robots/vite.svg..."

echo "[3/5] Publishing assets (with --delete)..."

echo "[4/5] Committing changes..."

echo "[5/5] Pushing to origin/main..."


cd ~/cogmyra-web
npm run build

rsync -av ~/cogmyra-web/dist/index.html  ~/cogmyra-dev/docs/
rsync -av ~/cogmyra-web/dist/robots.txt  ~/cogmyra-dev/docs/
rsync -av ~/cogmyra-web/dist/vite.svg    ~/cogmyra-dev/docs/
rsync -av --delete ~/cogmyra-web/dist/assets/ ~/cogmyra-dev/docs/assets/

cd ~/cogmyra-dev
git add docs/index.html docs/robots.txt docs/vite.svg docs/assets
git commit -m "deploy(web): update landing build; keep policies/guide intact"
git push origin main
