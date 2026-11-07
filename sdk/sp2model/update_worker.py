"""Hidden release-metadata worker; no native bridge or game/profile operations."""
import argparse
from .updates import Updates, _release_lease


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True)
    parser.add_argument('--lease', required=True)
    args = parser.parse_args()
    service = Updates(home=args.home)
    lock = service._path(service._config()).with_suffix('.worker')
    try:
        service.check()
    finally:
        _release_lease(lock, args.lease)


if __name__ == '__main__':
    main()
