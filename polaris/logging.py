import inspect


def log_method_call(method, logger):
    """
    Log the module path and file path of a call to a method, e.g.::

      polaris calling: polaris.landice.tasks.dome.decomposition_test.DecompositionTest.run()
        in /turquoise/usr/projects/climate/mhoffman/mpas/polaris/polaris/landice/tasks/dome/decomposition_test/__init__.py

    Parameters
    ----------
    method : method
        The method of a class that will be run immediately following this call

    logger: logging.Logger
        The logger to log the method path and file path to
    """  # noqa: E501
    if not inspect.ismethod(method):
        raise ValueError('The "method" argument must be a method')

    method_name = method.__name__

    # the class of whatever object the method belongs to might not be the
    # class where the method is implemented.  The "child" class is the class
    # of the object itself (typically a specific test case or step).  The
    # "actual" class where the method is implemented could be that class or
    # one of its parents.

    # get the "child" class and its location (import sequence) from the method
    child_class = method.__self__.__class__
    child_location = f'{child_class.__module__}.{child_class.__name__}'

    # iterate over the classes that the child class descends from to find the
    # first one that actually implements the given method.
    actual_class = None
    # inspect.getmro() returns a list of classes the child class descends from,
    # starting with the child class itself and going "back" to the "object"
    # class that all python classes descend from.
    for cls in inspect.getmro(child_class):
        if method.__name__ in cls.__dict__:
            actual_class = cls
            break

    if actual_class is None:
        raise ValueError(
            f'Hmm, it seems that none of {child_location} or its '
            f'parent classes implements\n the {method_name} '
            f'method, how strange!'
        )
    actual_location = f'{actual_class.__module__}.{actual_class.__name__}'

    # not every class is defined in a file (e.g. python intrinsics) but we
    # expect they always are in polaris.  Still we'll check to make sure.
    try:
        class_file = inspect.getfile(actual_class)
    except TypeError:
        class_file = None

    # log what we found out
    logger.info(f'polaris calling: {child_location}.{method_name}()')
    if child_location != actual_location:
        # okay, so we're inheriting this method from somewhere else.  Better
        # let the user know.
        logger.info(f'  inherited from: {actual_location}.{method_name}()')
    if class_file is not None:
        logger.info(f'  in {class_file}')


def log_function_call(function, logger):
    """
    Log the module path and file path of a call to a function, e.g.::

      polaris calling: polaris.parallel.set_cores_per_node()
        in /home/xylar/code/polaris/polaris/polaris/parallel.py

    Parameters
    ----------
    function : function
        The function that will be run immediately following this call

    logger: logging.Logger
        The logger to log the function path and file path to
    """
    if not inspect.isfunction(function):
        raise ValueError('The "function" argument must be a function')

    filename = inspect.getfile(function)

    # log what we found out
    logger.info(
        f'polaris calling: {function.__module__}.{function.__name__}()'
    )
    logger.info(f'  in {filename}')
