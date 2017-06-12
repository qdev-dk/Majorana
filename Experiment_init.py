from time import sleep
from functools import partial

import qcodes as qc

from qcodes.instrument_drivers.QDev.QDac import QDac
from qcodes.instrument_drivers.stanford_research.SR830 import SR830
from qcodes.instrument_drivers.Keysight.Keysight_33500B import Keysight_33500B
from qcodes.instrument_drivers.Keysight.Keysight_34465A import Keysight_34465A
from qcodes.instrument_drivers.ZI.ZIUHFLI import ZIUHFLI
from qcodes.instrument_drivers.devices import VoltageDivider

from .configreader import Config

from qcodes.instrument.parameter import ManualParameter
from qcodes.instrument.parameter import StandardParameter
from qcodes.utils.validators import Enum
from qcodes.utils.wrappers import init, _plot_setup, _save_individual_plots
from qcodes.instrument_drivers.tektronix.AWGFileParser import parse_awg_file

import qcodes.instrument_drivers.tektronix.Keithley_2600 as keith
import qcodes.instrument_drivers.rohde_schwarz.SGS100A as sg
import qcodes.instrument_drivers.tektronix.AWG5014 as awg
import qcodes.instrument_drivers.HP .HP8133A as hpsg

import logging
import re
import time
from functools import partial

import numpy as np

from qcodes import IPInstrument, MultiParameter
from qcodes.utils.validators import Enum
from qcodes.instrument_drivers.oxford.mercuryiPS import MercuryiPS

init_log = logging.getLogger(__name__)

# import T10_setup as t10
config = Config('./MajoQubit/sample.config')

# Subclass the SR830


class SR830_T10(SR830):
    """
    An SR830 with a Voltage divider absorbed into it
    """

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        # using the vocabulary of the config file
        self.ivgain = 1
        self.acfactor = 1

        self.amplitude_true = VoltageDivider(self.amplitude,
                                             self.acfactor)

        self.add_parameter('g',
                           label='{} conductance'.format(self.name),
                           # use lambda for late binding
                           get_cmd=lambda : self.get_conductance(self.amplitude_true(),
                                                                 self.ivgain),
                           unit='e^2/h',
                           get_parser=float)

    def _get_conductance(self, ac_excitation, iv_conv):
        """
        get_cmd for conductance parameter
        """
        resistance_quantum = 25.818e3  # [Ohm]
        i = self.X() / iv_conv
        # ac excitation voltage at the sample
        v_sample = ac_excitation()

        return (i/v_sample)*resistance_quantum

    @property
    def acfactor(self):
        return self.__acf

    @acfactor.setter
    def acfactor(self, acfactor):
        self.__acf = acfactor
        self.amplitude_true.division_value = acfactor


# Subclass the QDAC


class QDAC_T10(QDac):
    """
    A QDac with three voltage dividers
    """
    def __init__(self, name, address, config, **kwargs):
        super().__init__(name, address, **kwargs)

        # Define the named channels

        topo_channel = int(config.get('Channel Parameters',
                                      'topo bias channel'))
        topo_channel = self.parameters['ch{:02}_v'.format(topo_channel)]

        sens_r_channel = int(config.get('Channel Parameters',
                                        'right sensor bias channel'))
        sens_r_channel = self.parameters['ch{:02}_v'.format(sens_r_channel)]

        sens_l_channel = int(config.get('Channel Parameters',
                                        'left sensor bias channel'))
        sens_l_channel = self.parameters['ch{:02}_v'.format(sens_l_channel)]

        self.topo_bias = VoltageDivider(topo_channel,
                                        float(config.get('Gain settings',
                                                         'dc factor topo')))
        self.sens_r_bias = VoltageDivider(sens_r_channel,
                                          float(config.get('Gain settings',
                                                           'dc factor right')))
        self.sens_l_bias = VoltageDivider(sens_l_channel,
                                          float(config.get('Gain settings',
                                                           'dc factor left')))


# Subclass the DMM


class Keysight_34465A_T10(Keysight_34465A):

    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, **kwargs)

        self.iv_conv = 1

        self.add_parameter('ivconv',
                           label='Current',
                           unit='pA',
                           get_cmd=self._get_current,
                           set_cmd=None)

    def _get_current(self):
        """
        get_cmd for dmm readout of IV_TAMP parameter
        """
        return self.volt()/self.iv_conv*1E12


# Initialisation of intruments
qdac = QDAC_T10('qdac', 'ASRL6::INSTR', config, update_currents=False)
lockin_topo = SR830_T10('lockin_topo', 'GPIB10::7::INSTR')
lockin_right = SR830_T10('lockin_r', 'GPIB10::10::INSTR')
lockin_left = SR830_T10('lockin_l', 'GPIB10::14::INSTR')
zi = ZIUHFLI('ziuhfli', 'dev2189')

sg1 = sg.RohdeSchwarz_SGS100A("sg1","TCPIP0::192.168.15.107::inst0::INSTR")
keysightgen_left = Keysight_33500B('keysight_gen_left', 'TCPIP0::192.168.15.101::inst0::INSTR')
keysightgen_mid = Keysight_33500B('keysighDRt_gen_mid', 'TCPIP0::192.168.15.114::inst0::INSTR')
keysightgen_right = Keysight_33500B('keysight_gen_right', 'TCPIP0::192.168.15.109::inst0::INSTR')

keysightdmm_top = Keysight_34465A('keysight_dmm_top', 'TCPIP0::192.168.15.111::inst0::INSTR')
keysightdmm_mid = Keysight_34465A('keysight_dmm_mid', 'TCPIP0::192.168.15.112::inst0::INSTR')
keysightdmm_bot = Keysight_34465A('keysight_dmm_bot', 'TCPIP0::192.168.15.113::inst0::INSTR')

#keithleytop=keith.Keithley_2600('keithley_top', 'TCPIP0::192.168.15.116::inst0::INSTR',"a,b")
keithleybot=keith.Keithley_2600('keithley_bot', 'TCPIP0::192.168.15.115::inst0::INSTR',"a,b")

mercury = MercuryiPS(name='mercury', address='192.168.15.102', port=7020, axes=['X', 'Y', 'Z'])

hpsg1 = hpsg.HP8133A("hpsg1", 'GPIB10::4::INSTR')
awg1 = awg.Tektronix_AWG5014('AWG1', 'TCPIP0::192.168.15.105::inst0::INSTR', timeout=40)
awg2 = awg.Tektronix_AWG5014('AWG2', 'TCPIP0::192.168.15.106::inst0::INSTR', timeout=180)
CODING_MODE = False

# NOTE (giulio) this line is super important for metadata
# if one does not put the intruments in here there is no metadata!!
if CODING_MODE:
    init_log.critical('You are currently in coding mode - instruments are not ' +
                      'bound to Station and hence not logged properly.')
else:
    print('Querying all instrument parameters for metadata. This may take a while...')
    STATION = qc.Station(qdac, lockin_topo, lockin_right, lockin_left,
                         keysightgen_left, keysightgen_mid, keysightgen_right,
                         keysightdmm_top, keysightdmm_mid, keysightdmm_bot,
                         awg1, awg2, sg1, zi,
                         keithleybot, mercury, hpsg1)

# Initialisation of the experiment

qc.init("./MajoQubit", "DVZ_004d1", STATION)
