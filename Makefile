# CAR_OCI_REGISTRY_HOST and PROJECT are combined to define
# the Docker tag for this project. The definition below inherits the standard
# value for CAR_OCI_REGISTRY_HOST = artefact.skao.int and overwrites
# PROJECT to give a final Docker tag
#
PROJECT = ska-low-cbf-sw-cnic

# Fixed variables
# Timeout for gitlab-runner when run locally
TIMEOUT = 86400

CI_PROJECT_DIR ?= .
CI_PROJECT_PATH_SLUG ?= ska-low-cbf-sw-cnic
CI_ENVIRONMENT_SLUG ?= ska-low-cbf-sw-cnic

# TODO - remove this after the code has been refactored & cleaned-up
PYTHON_SWITCHES_FOR_PYLINT=--fail-under=6

# define private overrides for above variables in here
-include PrivateRules.mak

# Include the required modules from the SKA makefile submodule
include .make/docs.mk
include .make/help.mk
include .make/python.mk
include .make/make.mk
include .make/release.mk
