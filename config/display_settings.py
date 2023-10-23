import json

from config.initialize import settings


def display_settings(indent: int = 4):
    try:
        settings_dict = settings.to_dict()
        formatted_settings = json.dumps(settings_dict, indent=indent)
        print(formatted_settings)
    except Exception as e:
        print(f"Error displaying settings: {e}")


if __name__ == "__main__":
    display_settings()
