@ECHO OFF
REM A minimal Makefile for Sphinx documentation.
REM The %~dp0 extracts the directory where this script is located from its path.

SET SPHINXOPTS=%*
SET SPHINXBUILD=sphinx-build
SET SOURCEDIR=source
SET BUILDDIR=build

%SPHINXBUILD% -M %1 %SOURCEDIR% %BUILDDIR% %SPHINXOPTS%
