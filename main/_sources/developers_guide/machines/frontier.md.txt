# Frontier

## frontier, craygnu

If you've set things up for this compiler, you should be able to source a load
script similar to:

```bash
source load_dev_polaris_0.6.0-alpha.1_frontier_craygnu_mpich.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] gnu-cray
```

## frontier, craycray

Similarly to `craygnu`, for `craycray`, if you've set things up right, sourcing
the load scrip will look something like:

```bash
source load_dev_polaris_0.6.0-alpha.1_frontier_craycray_mpich.sh
```

To build MPAS components, use:

```bash
make [DEBUG=true] cray-cray
```
