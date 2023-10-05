This repository contains a list of tests in the Salt Test Suite that are **not** executed. Skipping
tests is bad and should only be used as a last resort.

The list is formatted using the TOML markup language and skipped tests are grouped by file/test level and then by "type". Missing
groups are taken as empty lists, they do  not have t be listed explicitely.

TODO:
- document format, how to use it
- currently requires python + toml. this is not always installed, should we add a dependency or try to find the bundle python interpreter?