# CTest dashboard script for Omega, driven by utils/omega/ctest/omega_ctest.py
#
# The three stages are separate ctest invocations so that the build can run
# on a login node and the tests in a batch job.  Each stage appends to the
# same Testing/<tag> directory, which the build stage creates.
#
# Variables passed with -D:
#   STAGE                     build | test | submit
#   CTEST_SOURCE_DIRECTORY    components/omega in the Omega branch
#   CTEST_BINARY_DIRECTORY    the Omega build directory
#   CTEST_SITE                the site name shown on CDash
#   CTEST_BUILD_NAME          the build name shown on CDash
#   CTEST_MODEL               Nightly, Experimental or Continuous
#   CTEST_NIGHTLY_START_TIME  the CDash project's nightly start time
#   CTEST_BUILD_COMMAND       the build command (build stage only)
#   CTEST_SUBMIT_URL          the CDash submit URL
#   SUBMIT                    ON to submit at the end of the test stage

cmake_minimum_required(VERSION 3.20)

foreach(var STAGE CTEST_SOURCE_DIRECTORY CTEST_BINARY_DIRECTORY CTEST_SITE
            CTEST_BUILD_NAME CTEST_MODEL CTEST_NIGHTLY_START_TIME
            CTEST_SUBMIT_URL)
  if(NOT DEFINED ${var})
    message(FATAL_ERROR "${var} must be passed with -D")
  endif()
endforeach()

set(CTEST_DROP_SITE_CDASH TRUE)

# ctest_build() needs the generator even when the build command is explicit
file(STRINGS "${CTEST_BINARY_DIRECTORY}/CMakeCache.txt" _generator_line
     REGEX "^CMAKE_GENERATOR:INTERNAL=")
string(REGEX REPLACE "^CMAKE_GENERATOR:INTERNAL=" "" CTEST_CMAKE_GENERATOR
       "${_generator_line}")

if(STAGE STREQUAL "build")
  if(NOT DEFINED CTEST_BUILD_COMMAND)
    message(FATAL_ERROR "CTEST_BUILD_COMMAND must be passed with -D")
  endif()
  ctest_start(${CTEST_MODEL})
  ctest_build(RETURN_VALUE _build_result NUMBER_ERRORS _build_errors)
  if(NOT _build_result EQUAL 0 OR _build_errors GREATER 0)
    message(FATAL_ERROR "Omega build failed: ${_build_errors} error(s)")
  endif()

elseif(STAGE STREQUAL "test")
  # append to the build stage's tag when there was one; an existing build
  # reused with -p has no build stage
  if(EXISTS "${CTEST_BINARY_DIRECTORY}/Testing/TAG")
    ctest_start(${CTEST_MODEL} APPEND)
  else()
    ctest_start(${CTEST_MODEL})
  endif()
  ctest_test(RETURN_VALUE _test_result)
  if(SUBMIT)
    ctest_submit(RETURN_VALUE _submit_result)
    if(NOT _submit_result EQUAL 0)
      message(FATAL_ERROR "CDash submission failed")
    endif()
  endif()
  if(NOT _test_result EQUAL 0)
    message(FATAL_ERROR "Some Omega tests failed")
  endif()

elseif(STAGE STREQUAL "submit")
  ctest_start(${CTEST_MODEL} APPEND)
  ctest_submit(RETURN_VALUE _submit_result)
  if(NOT _submit_result EQUAL 0)
    message(FATAL_ERROR "CDash submission failed")
  endif()

else()
  message(FATAL_ERROR "Unknown STAGE '${STAGE}'; expected build, test or submit")
endif()
