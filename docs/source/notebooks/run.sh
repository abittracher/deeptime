#!/bin/bash
find . -maxdepth 1 -name \*.ipynb -exec sh -c \
  'for i do  jupyter nbconvert --to notebook --execute $i --inplace ; done' sh {} \;
