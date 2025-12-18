(dev-building-docs)=

# Building the Documentation

As long as you have followed the procedure in {ref}`dev-conda-env` for setting
up your conda environment, you will already have the packages available that
you need to build the documentation.

Then, run the following script to build the docs:

```bash
cd docs
DOCS_VERSION=test make clean versioned-html
```

# Previewing the Documentation

To preview the documentation locally, open the `index.html` file in the
`_build/html/test` directory with your browser or try:

```bash
  cd _build/html
  python -m http.server 8000
```

Then, open http://0.0.0.0:8000/test/ in your browser.
