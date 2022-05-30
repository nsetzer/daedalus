
import os
import sys
import argparse
import logging

from .cli import register_parsers, Repl

def getArgs():
    parser = argparse.ArgumentParser(
        description='unopinionated javascript framework')
    subparsers = parser.add_subparsers()
    parser.add_argument('--verbose', '-v', action='count', default=0)
    register_parsers(subparsers)
    args = parser.parse_args()

    return parser, args

def main():

    if Repl is not None and len(sys.argv) == 1:
        # if no arguments are given and bytecode is available
        # run the bytecode REPL
        Repl().main()
    else:
        parser, args = getArgs()

        FORMAT = '%(levelname)-8s - %(message)s'
        logging.basicConfig(level=logging.INFO, format=FORMAT)

        rv = 0
        if not hasattr(args, 'func'):
            parser.print_help()
        else:
            rv = args.func(args)

        if rv:
            sys.exit(rv)

if __name__ == '__main__':
    main()