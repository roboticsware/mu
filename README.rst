Custom Mu - Custom version of A Simple Python Code Editor `Mu <https://madewith.mu/>`_ 
================================

[How to make dev env.]

1. install miniconda

``https://docs.conda.io/projects/miniconda/en/latest/miniconda-install.html`` 

2. Create virtual environment 

``conda create -n mu python=3.8``

3. Activate the created virtual env. 

``conda activate mu`` 

4. Clone source codes 

``git clone https://github.com/roboticsware/mu``

5. Enter the directory of source codes 

``cd mu``  

6. Install dev dependencies 

``pip install -e ".[dev]"``

7. Run Mu 

``python run.py``

8. Build Mu

``make win64 or macos``


You can also reivew more information about extensive developer documentation `here <https://mu.readthedocs.io/>`_.





