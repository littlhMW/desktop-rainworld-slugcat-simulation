# SlugcatPet Extended

An extended Rain World desktop pet based on `lingxiaojun/slugcatpet`, focused on expanding creatures, objects, behaviors, environmental systems, and scene state.

## Extensions

- **More creatures**: Lizards, Squidcada, Noodleflies, Slugpups, and more.
- **More objects**: Pearls, spears, rocks, food, Karma Flowers, poles, with expanded grabbing, carrying, throwing, and object interactions.
- **More behaviors**: Extended creature behavior, social interactions, chasing, fleeing, climbing, flying, and object interaction.
- **Environmental systems**: Rain-cycle timer, rain sleep, shelters, and related creature state handling.
- **Scene persistence**: Save and restore world state and object state.
- **Removed item limits**: Removes the original item-count limits and includes performance improvements.

## Requirements

- Windows 10 / 11
- Python 3.10+
- Rain World
- Downpour / More Slugcats DLC

Running from source requires a local Rain World installation. On first launch, select the Rain World installation directory so the program can read the required local assets.

## Installation

```powershell
pip install -e .
python run_slugcatpet.py
```

To build a Windows executable:

```powershell
.\build_exe.ps1
```

The exact output location depends on the build script.

## Basic Controls

- Select an object from the toolbar and click in the window to place it.
- Press `Esc` or right-click to cancel the current action.
- Drag objects to move, carry, or throw them.
- Use the eraser to remove objects or the clear function to clear scene objects.
- Create shelters by dragging an area; the shelter size follows the dragged area.
- A built-in rain-cycle timer can be manually started or stopped from the environment panel.

## Characters

Currently included:

- Monk
- Survivor
- Rivulet
- Watcher
- Gourmand
- Hunter
- Artificer
- Spearmaster
- Saint
- Slugpup

## Project Origin

This project is an extended derivative of `lingxiaojun/slugcatpet` and is maintained independently.

Rain World and its game assets belong to their respective rights holders. This repository does not distribute Rain World game assets; the program reads required assets from the user's local installation.

## License

The source code is licensed under the MIT License. See [LICENSE](LICENSE).
