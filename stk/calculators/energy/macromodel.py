from uuid import uuid4
import os
import subprocess as sp

from ...utilities import move_generated_macromodel_files
from .energy_calculators import EnergyCalculator, EnergyError


class MacroModelEnergy(EnergyCalculator):
    """
    Calculates the energy using MacroModel.

    """

    def __init__(
        self,
        macromodel_path,
        output_dir=None,
        force_field=16,
        use_cache=False
    ):
        """
        Initialize a :class:`.MacroModelEnergy` instance.

        Parameters
        ----------
        macromodel_path : :class:`str`
            The full path of the Schrodinger suite within the user's
            machine. For example, on a Linux machine this may be
            something like ``'/opt/schrodinger2017-2'``.

        output_dir : :class:`str`, optional
            The name of the directory into which files generated during
            the optimization are written, if ``None`` then
            :func:`uuid.uuid4` is used.

        force_field : :class:`int`, optional
            The number of the force field to be used.

        use_cache : :class:`bool`, optional
            If ``True`` :meth:`get_energy` will not run twice on the
            same molecule, but will instead return the previously
            calculated value.

        """

        self._macromodel_path = macromodel_path
        self._output_dir = output_dir
        self._force_field = force_field
        super().__init__(use_cache=use_cache)

    def get_energy(self, mol):
        """
        Calculate the energy of `mol`.

        Parameters
        ----------
        mol : :class:`.Molecule`
            The :class:`.Molecule` whose energy is to be calculated.

        Returns
        -------
        :class:`float`
            The energy.

        Raises
        ------
        :class:`EnergyError`
            This exception is raised if no energy value is found in the
            MacroModel calculation's ``.log`` file. Likely due to a
            forcefield error.

        """

        # To prevent conflicts when running this function in parallel,
        # a temporary copy of the molecular structure file is made and
        # used for macromodel calculations.

        # Unique file name is generated by inserting a random int into
        # the file path.
        basename = str(uuid4().int)
        if self._output_dir is None:
            output_dir = basename
        else:
            output_dir = self._output_dir

        tmp_file = f'{basename}.mol'
        mol.write(tmp_file)

        convrt_app = os.path.join(
            self._macromodel_path, 'utilities', 'structconvert'
        )
        convrt_cmd = [
            convrt_app, tmp_file, f'{basename}.mae'
        ]
        sp.call(convrt_cmd, stdout=sp.PIPE, stderr=sp.PIPE)

        # Create an input file and run it.
        input_script = (
         "{0}.mae\n"
         "{0}-out.maegz\n"
         " MMOD       0      1      0      0     0.0000     "
         "0.0000     0.0000     0.0000\n"
         " FFLD{1:8}      1      0      0     1.0000     "
         "0.0000     0.0000     0.0000\n"
         " BGIN       0      0      0      0     0.0000     "
         "0.0000     0.0000     0.0000\n"
         " READ      -1      0      0      0     0.0000     "
         "0.0000     0.0000     0.0000\n"
         " ELST      -1      0      0      0     0.0000     "
         "0.0000     0.0000     0.0000\n"
         " WRIT       0      0      0      0     0.0000     "
         "0.0000     0.0000     0.0000\n"
         " END       0      0      0      0     0.0000     "
         "0.0000     0.0000     0.0000\n\n"
        ).format(basename, self._force_field)

        with open(f'{basename}.com', 'w') as f:
            f.write(input_script)

        cmd = [
            os.path.join(self._macromodel_path, 'bmin'),
            basename,
            "-WAIT",
            "-LOCAL"
        ]
        sp.call(cmd)

        # Check if the license was found. If not run the function
        # again.
        with open(f'{basename}.log', 'r') as f:
            log_content = f.read()

        if ('FATAL -96: Could not check out a license for mmlibs' in
           log_content):
            return self.get_energy(mol)

        # Read the .log file and return the energy.
        with open(f'{basename}.log', 'r') as f:
            for line in f:
                if "                   Total Energy =" in line:
                    eng = float(line.split()[-2].replace("=", ""))

        try:
            return eng
        except UnboundLocalError:
            raise EnergyError('MacroModel energy calculation failed.')

        finally:
            move_generated_macromodel_files(basename, output_dir)
