#!/usr/bin/env python
# coding=utf-8

# -------------------------------------------------------------------------------
#
#  ███████╗██████╗ ██╗ ██████╗███████╗██╗     ██╗██████╗
#  ██╔════╝██╔══██╗██║██╔════╝██╔════╝██║     ██║██╔══██╗
#  ███████╗██████╔╝██║██║     █████╗  ██║     ██║██████╔╝
#  ╚════██║██╔═══╝ ██║██║     ██╔══╝  ██║     ██║██╔══██╗
#  ███████║██║     ██║╚██████╗███████╗███████╗██║██████╔╝
#  ╚══════╝╚═╝     ╚═╝ ╚═════╝╚══════╝╚══════╝╚═╝╚═════╝
#
# Name:        ltsteps.py
# Purpose:     Process LTSpice output files and align data for usage in a spread-
#              sheet tool such as Excel, or Calc.
#
# Author:      Nuno Brum (nuno.brum@gmail.com)
#
# Licence:     refer to the LICENSE file
# -------------------------------------------------------------------------------

"""
This module allows to process data generated by LTSpice during simulation. There are three types of files that are
handled by this module.

    + log files - Files with the extension '.log' that are automatically generated during simulation, and that are
      normally accessible with the shortcut Ctrl+L after a simulation is ran.Log files are interesting for two reasons.

            1. If .STEP primitives are used, the log file contain the correspondence between the step run and the step
            value configuration.

            2. If .MEAS primitives are used in the schematic, the log file contains the measurements made on the output
            data.

      LTSteps.py can be used to retrieve both step and measurement information from log files.

    + txt files - Files exported from the Plot File -> Export data as text menu. This file is an text file where data is
      saved in the text format. The reason to use spicelib instead of another popular lib as pandas, is because the data
      format when .STEPS are used in the simulation is not not very practical. The spicelib LTSteps.py can be used to
      reformat the text, so that the run parameter is added to the data as an additional column instead of a table
      divider. Please Check LTSpiceExport class for more information.

    + mout files - Files generated by the Plot File -> Execute .MEAS Script menu. This command allows the user to run
      predefined .MEAS commands which create a .mout file. A .mout file has the measurement information stored in the
      following format:

      .. code-block:: text

            Measurement: Vout_rms
            step	RMS(V(OUT))	FROM	TO
             1	1.41109	0	0.001
             2	1.40729	0	0.001

            Measurement: Vin_rms
              step	RMS(V(IN))	FROM	TO
                 1	0.706221	0	0.001
                 2	0.704738	0	0.001

            Measurement: gain
              step	Vout_rms/Vin_rms
                 1	1.99809
                 2	1.99689


The LTSteps.py can be used directly from a command line by invoking python with the -m option as exemplified below.

.. code-block:: text

    $ python -m spicelib.LTSteps <path_to_filename>

If `<path_to_filename>` is a log file, it will create a file with the same name, but with extension .tout that is a
tab separated value (tsv) file, which contains the .STEP and .MEAS information collected.

If `<path_to_filename>` is a txt exported file, it will create a file with the same name, but with extension .tsv a
tab separated value (tsv) file, which contains data reformatted with the step number as one of the columns. Please
consult the reformat_LTSpice_export() function for more information.

If `<path_to_filename>` is a mout file, it will create a file with the same name, but with extension .tmout that is a
tab separated value (tsv) file, which contains the .MEAS information collected, but adding the STEP run information
as one of the columns.

If `<path_to_filename>` argument is ommited, the script will automatically search for the newest .log/.txt/.mout file
and use it.

"""
__author__ = "Nuno Canto Brum <me@nunobrum.com>"
__copyright__ = "Copyright 2023, Fribourg Switzerland"

import dataclasses
import os.path
import re
from typing import List

from .logfile_data import LogfileData, try_convert_value
from ..utils.detect_encoding import detect_encoding
import logging
_logger = logging.getLogger("spicelib.LTSteps")


def reformat_LTSpice_export(export_file: str, tabular_file: str):
    """
    Reads an LTSpice File Export file and writes it back in a format that is more convenient for data treatment.

    When using the "Export data as text" in the raw file menu the data is already exported in a tabular format.
    However, if steps are being used, the step information doesn't appear on the table.  Instead the successive STEP
    runs are stacked on one after another, separated by the following text:

    .. code-block:: text

        Step Information: Ton=400m  (Run: 2/2)

    What would be desirable would be that the step number (Run number) and the STEP variable would be placed within the
    columns.  This allows, for example, using Excel functionality known as Pivot Tables to filter out data, or some other
    database selection function.
    The tab is chosen as separator because it is normally compatible with pasting data into Excel.

    :param export_file: Filename of the .txt file generated by the "Export Data as Text"
    :type export_file: str
    :param tabular_file: Filename of the tab separated values (TSV) file that
    :type tabular_file: str
    :return: Nothing
    :rtype: None

    """
    encoding = detect_encoding(export_file)
    fin = open(export_file, 'r', encoding=encoding)
    fout = open(tabular_file, 'w', encoding=encoding)

    headers = fin.readline()
    # writing header
    go_header = True
    run_no = 0  # Just to avoid warning, this is later overridden by the step information
    param_values = ""  # Just to avoid warning, this is later overridden by the step information
    regx = re.compile(r"Step Information: ([\w=\d\. -]+) +\(Run: (\d*)/\d*\)\n")
    for line in fin:
        if line.startswith("Step Information:"):
            match = regx.match(line)
            if match:
                step, run_no = match.groups()
                params = []
                for param in step.split():
                    params.append(param.split('=')[1])
                param_values = "\t".join(params)

                if go_header:
                    header_keys = []
                    for param in step.split():
                        header_keys.append(param.split('=')[0])
                    param_header = "\t".join(header_keys)
                    msg = "Run\t%s\t%s" % (param_header, headers)
                    fout.write(msg)
                    _logger.debug(msg)
                    go_header = False
        else:
            fout.write("%s\t%s\t%s" % (run_no, param_values, line))

    fin.close()
    fout.close()


class LTSpiceExport(object):
    """
    Opens and reads LTSpice export data when using the "Export data as text" in the File Menu on the waveform window.

    The data is then accessible by using the following attributes implemented in this class.

    :property headers: list containing the headers on the exported data
    :property dataset: dictionary in which the keys are the the headers and the export file and the values are
        lists. When reading STEPed data, a new key called 'runno' is added to the dataset.

    **Examples**

    ::

        export_data = LTSpiceExport("export_data_file.txt")
        for value in export_data.dataset['I(V1)']:
            print(f"Do something with this value {value}")

    :param export_filename: path to the Export file.
    :type export_filename: str
    """

    def __init__(self, export_filename: str):
        self.encoding = detect_encoding(export_filename)
        fin = open(export_filename, 'r', encoding=self.encoding)
        file_header = fin.readline()

        self.headers = file_header.split('\t')
        # Set to read header
        go_header = True

        curr_dic = {}
        self.dataset = {}

        regx = re.compile(r"Step Information: ([\w=\d\. -]+) +\(Run: (\d*)/\d*\)\n")
        for line in fin:
            if line.startswith("Step Information:"):
                match = regx.match(line)
                if match:
                    step, run_no = match.groups()
                    curr_dic['runno'] = run_no
                    for param in step.split():
                        key, value = param.split('=')
                        curr_dic[key] = try_convert_value(value)

                    if go_header:
                        go_header = False  # This is executed only once
                        for key in self.headers:
                            self.dataset[key] = []  # Initializes an empty list

                        for key in curr_dic:
                            self.dataset[key] = []  # Initializes an empty list

            else:
                values = line.split('\t')

                for key in curr_dic:
                    self.dataset[key].append(curr_dic[key])

                for i in range(len(values)):
                    self.dataset[self.headers[i]].append(try_convert_value(values[i]))

        fin.close()


@dataclasses.dataclass
class HarmonicData:
    harmonic_number: int
    frequency: float
    fourier_component: float
    normalized_component: float
    phase: float
    normalized_phase: float
    # units: dict = dataclasses.field(default_factory=dict)

    @classmethod
    def from_line(cls, line: str):
        tokens = line.split()
        harmonic_number = int(tokens[0])
        frequency = float(tokens[1])
        fourier_component = float(tokens[2])
        normalized_component = float(tokens[3])
        phase = float(tokens[4].rstrip('°'))
        normalized_phase = float(tokens[5].rstrip('°'))
        return cls(harmonic_number, frequency, fourier_component, normalized_component, phase, normalized_phase)


@dataclasses.dataclass
class FourierData:
    signal: str
    n_periods: int
    dc_component: float
    phd: float  # Partial Harmonic Distortion
    thd: float  # Total Harmonic Distortion
    harmonics: List[HarmonicData]
    step: int

    @property
    def fundamental(self):
        return self.harmonics[0].frequency

    def __getitem__(self, item):
        return self.harmonics[item]

    def __iter__(self):
        return iter(self.harmonics)

    def __len__(self):
        return len(self.harmonics)


class LTSpiceLogReader(LogfileData):
    """
    Reads an LTSpice log file and retrieves the step information if it exists. The step information is then accessible
    by using the 'stepset' property of this class.
    This class is intended to be used together with the RawRead to retrieve the runs that are associated with a
    given parameter setting.

    This class constructor only reads the step information of the log file. If the measures are needed, then the user
    should call the get_measures() method.

    :property stepset: dictionary in which the keys are the variables that were STEP'ed during the simulation and
        the associated value is a list representing the sequence of assigned values during simulation.

    :property headers: list containing the headers on the exported data. This is only populated when the *read_measures*
        optional parameter is set to False.

    :property dataset: dictionary in which the keys are the headers and the export file and the values are
         lists. This is information is only populated when the *read_measures* optional parameter is set to False.

    :param log_filename: path to the Export file.
    :type log_filename: str
    :param read_measures: Optional parameter to skip measuring data reading.
    :type read_measures: boolean
    :param step_set: Optional parameter to provide the steps from another file. This is used to process .mout files.
    :type step_set: dict
    """

    def __init__(self, log_filename: str, read_measures=True, step_set: dict = None, encoding=None):
        super().__init__(step_set)
        self.logname = log_filename
        self.fourier = {}
        if encoding is None:
            self.encoding = detect_encoding(log_filename, "Circuit:")
        else:
            self.encoding = encoding

        # Preparing a stepless measurement read regular expression
        # there are only measures taken in the format parameter: measurement
        # A few examples of readings
        # vout_rms: RMS(v(out))=1.41109 FROM 0 TO 0.001  => Interval
        # vin_rms: RMS(v(in))=0.70622 FROM 0 TO 0.001  => Interval
        # gain: vout_rms/vin_rms=1.99809 => Parameter
        # vout1m: v(out)=-0.0186257 at 0.001 => Point
        # fcut: v(vout)=vmax/sqrt(2) AT 252.921
        # fcutac=8.18166e+006 FROM 1.81834e+006 TO 1e+007 => AC Find Computation
        regx = re.compile(
                # r"^(?P<name>\w+)(:\s+.*)?=(?P<value>[\d(inf)\.E+\-\(\)dB,°]+)(( FROM (?P<from>[\d\.E+-]*) TO (?P<to>[\d\.E+-]*))|( at (?P<at>[\d\.E+-]*)))?",
                r"^(?P<name>\w+)(:\s+.*)?=(?P<value>[\d(inf)E+\-\(\)dB,°(-/\w]+)( FROM (?P<from>[\d\.E+-]*) TO (?P<to>[\d\.E+-]*)|( at (?P<at>[\d\.E+-]*)))?",
                re.IGNORECASE)

        _logger.debug(f"Processing LOG file:{log_filename}")
        with open(log_filename, 'r', encoding=self.encoding) as fin:
            line = fin.readline()

            while line:
                if line.startswith("N-Period"):
                    # Read number of periods
                    n_periods = line.strip('\r\n').split("=")[-1]
                    if n_periods == 'all':
                        n_periods = -1
                    else:
                        n_periods = float(n_periods)
                    # Read signal name
                    line = fin.readline().strip('\r\n')
                    signal = line.split(" of ")[-1]
                    # Read DC component
                    line = fin.readline().strip('\r\n')
                    dc_component = float(line.split(':')[-1])
                    # Skip blank line
                    fin.readline()
                    # Skip two header lines
                    fin.readline()
                    fin.readline()
                    # Read Harmonics table
                    phd = thd = None
                    harmonics = []
                    while True:
                        line = fin.readline().strip('\r\n')
                        if line.startswith("Total Harmonic"):
                            # Find THD
                            thd = float(re.search(r"\d+.\d+", line).group())
                        elif line.startswith("Partial Harmonic"):
                            # Find PHD
                            phd = float(re.search(r"\d+.\d+", line).group())
                        elif line == "":
                            # End of the table
                            break
                        else:
                            harmonics.append(HarmonicData.from_line(line))

                    fourier_data = FourierData(signal, n_periods, dc_component, phd, thd, harmonics, self.step_count - 1)
                    if signal in self.fourier:
                        self.fourier[signal].append(fourier_data)
                    else:
                        self.fourier[signal] = [fourier_data]

                if line.startswith(".step"):
                    self.step_count += 1
                    tokens = line.strip('\r\n').split(' ')
                    for tok in tokens[1:]:
                        lhs, rhs = tok.split("=")
                        # Try to convert to int or float
                        rhs = try_convert_value(rhs)

                        ll = self.stepset.get(lhs, None)
                        if ll:
                            ll.append(rhs)
                        else:
                            self.stepset[lhs] = [rhs]

                elif line.startswith("Measurement:"):
                    if not read_measures:
                        fin.close()
                        return
                    else:
                        break  # Jumps to the section that reads measurements

                if self.step_count == 0:  # then there are no steps,
                    match = regx.match(line)
                    if match:
                        # Get the data
                        dataname = match.group('name')
                        if match.group('from'):
                            headers = [dataname, dataname + "_FROM", dataname + "_TO"]
                            measurements = [match.group('value'), match.group('from'), match.group('to')]
                        elif match.group('at'):
                            headers = [dataname, dataname + "_at"]
                            measurements = [match.group('value'), match.group('at')]
                        else:
                            headers = [dataname]
                            measurements = [match.group('value')]
                        self.measure_count += 1
                        for k, title in enumerate(headers):
                            self.dataset[title] = [
                                try_convert_value(measurements[k])]  # need to be a list for compatibility
                line = fin.readline()

            dataname = None

            headers = []  # Initializing an empty parameters
            measurements = []
            while line:
                line = line.strip('\r\n')
                if line.startswith("Measurement: "):
                    if dataname:  # If previous measurement was saved
                        # store the info
                        if len(measurements):
                            _logger.debug("Storing Measurement %s (count %d)" % (dataname, len(measurements)))
                            self.measure_count += len(measurements)
                            for k, title in enumerate(headers):
                                self.dataset[title] = [measure[k] for measure in measurements]
                        headers = []
                        measurements = []
                    dataname = line[13:]  # text which is after "Measurement: ". len("Measurement: ") -> 13
                    _logger.debug("Reading Measurement %s" % line[13:])
                else:
                    tokens = line.split("\t")
                    if len(tokens) >= 2:
                        try:
                            int(tokens[0])  # This instruction only serves to trigger the exception
                            meas = tokens[1:]  # remove the first token
                            measurements.append(try_convert_value(meas))
                            self.measure_count += 1
                        except ValueError:
                            if len(tokens) >= 3 and (tokens[2] == "FROM" or tokens[2] == 'at'):
                                tokens[2] = dataname + '_' + tokens[2]
                            if len(tokens) >= 4 and tokens[3] == "TO":
                                tokens[3] = dataname + "_TO"
                            headers = [dataname] + tokens[2:]
                            measurements = []
                    else:
                        _logger.debug("->" + line)

                line = fin.readline()  # advance to the next line

            # storing the last data into the dataset
            if dataname:
                _logger.debug("Storing Measurement %s (count %d)" % (dataname, len(measurements)))
            if len(measurements):
                self.measure_count += len(measurements)
                for k, title in enumerate(headers):
                    self.dataset[title] = [measure[k] for measure in measurements]

            _logger.debug("%d measurements" % len(self.dataset))
            _logger.info("Identified %d steps, read %d measurements" % (self.step_count, self.measure_count))

    def export_data(self, export_file: str, encoding=None, append_with_line_prefix=None):
        """Aside from exporting the data, it also exports fourier data if it exists"""
        super().export_data(export_file, encoding, append_with_line_prefix)

        fourier_export_file = os.path.splitext(export_file)[0] + "_fourier.txt"
        if self.fourier:
            with open(fourier_export_file, "w", encoding=encoding) as fout:
                if self.step_count > 0:
                    fout.write("\t".join(self.stepset.keys()) + "\t")
                fout.write("Signal\tN-Periods\tDC Component\tFundamental\tN-Harmonics\tPHD\tTHD\n")
                for signal in self.fourier:
                    if self.step_count > 0:
                        for step_no in range(self.step_count):
                            step_values = [f"{self.stepset[step][step_no]}" for step in self.stepset]
                            for analysis in self.fourier[signal]:
                                if analysis.step == step_no:
                                    fout.write('\t'.join(step_values) + '\t')
                                    if analysis.n_periods < 1:
                                        n_periods = 'all'
                                    else:
                                        n_periods = analysis.n_periods
                                    fout.write(f"{signal}\t"
                                               f"{n_periods}\t"
                                               f"{analysis.dc_component}\t"
                                               f"{analysis.fundamental}\t"
                                               f"{len(analysis)}\t"
                                               f"{analysis.phd}\t"
                                               f"{analysis.thd}\n")
                    else:
                        for analysis in self.fourier[signal]:
                            if analysis.n_periods == -1:
                                n_periods = 'all'
                            else:
                                n_periods = analysis.n_periods
                            fout.write(f"{signal}\t"
                                       f"{n_periods}\t"
                                       f"{analysis.dc_component}\t"
                                       f"{analysis.fundamental}"
                                       f"\t{len(analysis)}\t"
                                       f"{analysis.phd}\t"
                                       f"{analysis.thd}\n")
                fout.write("\n\nHarmonic Analysis\n")
                fout.write("\t".join(self.stepset.keys()) + "\t")
                fout.write("Signal\tN-Periods\tHarmonic\tFrequency\tFourier\tNormalized\tPhase\tNormalized\n")
                for signal in self.fourier:
                    for analysis in self.fourier[signal]:
                        if self.step_count > 0:
                            for step_no in range(self.step_count):
                                if analysis.step == step_no:
                                    step_values = [f"{self.stepset[step][step_no]}" for step in self.stepset]
                                    for harmonic in analysis:
                                        fout.write('\t'.join(step_values) + '\t')
                                        fout.write(
                                            f"{signal}\t"
                                            f"{analysis.n_periods}\t"
                                            f"{harmonic.harmonic_number}\t"
                                            f"{harmonic.frequency}\t"
                                            f"{harmonic.fourier_component}\t"
                                            f"{harmonic.normalized_component}\t"
                                            f"{harmonic.phase}\t"
                                            f"{harmonic.normalized_phase}\n"
                                        )
                        else:
                            for harmonic in analysis:
                                fout.write(f"{signal}\t"
                                           f"{analysis.n_periods}\t"
                                           f"{harmonic.harmonic_number}\t"
                                           f"{harmonic.frequency}\t"
                                           f"{harmonic.fourier_component}\t"
                                           f"{harmonic.normalized_component}\t"
                                           f"{harmonic.phase}\t"
                                           f"{harmonic.normalized_phase}\n"
                                           )
                fout.write("\n")
