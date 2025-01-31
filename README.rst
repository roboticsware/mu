Custom Mu - Custom version of A Simple Python Code Editor `Mu <https://madewith.mu/>`_ 
=======================================================================================

Additional new features
-----------------------
Pygame Zero
```````````
- Integrated `the enhanced Pygame Zero Helper Lib <https://github.com/roboticsware/pgzhelper>`_ to Mu
    .. image:: screenshots/pgzhelper.png
- Integrated `PyInstaller <https://pyinstaller.org>`_ to package and deploy your Pygame Zero Game project to one executable file
    .. image:: screenshots/pyinstaller.png

Respberry Pi Pico
`````````````````
- Enhanced the file manager for `Respberry Pi Pico board <https://www.raspberrypi.com/products/raspberry-pi-pico>`_
    - Navigation in the both local andd device file manager
    - Copy a file between both local andd device file manager
    - Delete a file in the local file manager 
- Enhanced the Start/Stop button to run your code directly on the RPi Pico
- Integrated `the enhanced Picozero Lib <https://picozero-rw.readthedocs.io>`_ to Mu
    - Manual install of PicoZero Lib by Drag-and-drop
        .. image:: screenshots/picozero.png


Editor
``````
- Shows a code-assitance of your own language by locale
    .. image:: screenshots/code-assistance.jpg
- Added new Shortcuts
    ==================  ======================
    Shortcuts           Functions    
    ==================  ======================  
    Ctrl(Cmd) + w       Close tab  
    Ctrl(Cmd) + , or .  Move letf or right tab
    ==================  ======================  
- Enhanced the Find function
    - Show the very word in the Find window based on your selected text


How to make dev env. and build
------------------------------

1. install miniconda

    ``https://docs.conda.io/projects/miniconda/en/latest/miniconda-install.html``

2. Temporarily set Conda to 32-bit forcibly

    ``Set CONDA_FORCE_32BIT=1``

3. Create virtual environment

    ``conda create -n mu python=3.7``

4. Activate the created virtual env.

    ``conda activate mu``

5. Clone source codes

    ``git clone https://github.com/roboticsware/mu``

6. Enter the directory of source codes

    ``cd mu``

7. Install dev dependencies

    ``pip install -e ".[dev]"``

8. Run Mu

    ``python run.py``

9. Build Mu

    ``make win32``


You can also reivew more information about extensive developer documentation `here <https://mu.readthedocs.io/>`_.





