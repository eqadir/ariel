#!/bin/bash
printf "\nCopying ariel sources for Docker build\n"
rm -rf ./ariel
cp -r ../ariel ./ariel
printf "\nCombining app and backend requirements.txt\n"
rm -f requirements.txt
cat ../requirements.txt > requirements.txt
echo '' >> requirements.txt
cat requirements-base.txt >> requirements.txt

