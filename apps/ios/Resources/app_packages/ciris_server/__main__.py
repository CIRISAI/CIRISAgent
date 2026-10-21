"""``python -m ciris_server`` → the same dispatch as the ``ciris-server`` script.

Used by the desktop launcher to spawn the headless node as a child process
(``python -m ciris_server serve``), and usable directly. Routes through
``cli.main`` so ``serve`` / ``--home`` / ``--key-id`` / ``import-traces`` /
``--server`` all reach the compiled node, while a bare ``python -m ciris_server``
opens the desktop UI just like the console script.
"""

from ciris_server.cli import main

if __name__ == "__main__":
    main()
