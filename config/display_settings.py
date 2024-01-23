from pprint import pprint

from config.initialize import settings


def display_settings(indent: int = 4):
    try:
        settings_dict = settings.to_dict()
        pprint(settings_dict, indent=indent)
    except Exception as e:
        print(f"Error displaying settings: {e}")


if __name__ == "__main__":
    display_settings()
