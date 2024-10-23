#!/bin/bash
rm -rf ariel
cp -r ../ariel .
rm requirements.txt
cp ../requirements.txt ./requirements.txt
echo "" >> ./requirements.txt
cat requirements-backend.txt >> ./requirements.txt
pip install -r requirements.txt
