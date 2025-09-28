#!/bin/zsh
set -e

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
