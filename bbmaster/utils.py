import yaml
import numpy as np
import os
from scipy.interpolate import interp1d
import pymaster as nmt
import healpy as hp
import sacc


def get_pcls(man, fnames, names, fname_out, mask, binning, winv=None):
    """
    man -> pipeline manager
    fnames -> files with input maps
    names -> map names
    fname_out -> output file name
    mask -> mask
    binning -> binning scheme to use
    winv -> inverse binned MCM (optional)
    """

    if winv is not None:
        nbpw = binning.get_n_bands()
        if winv.shape != (4, nbpw, 4, nbpw):
            raise ValueError("Incompatible binning scheme and "
                             "binned MCM.")
        winv = winv.reshape([4*nbpw, 4*nbpw])

    # Read maps
    fields = []
    for fname in fnames:
        mpQ, mpU = hp.read_map(fname, field=[0, 1])
        f = nmt.NmtField(mask, [mpQ, mpU])
        fields.append(f)
    nmaps = len(fields)

    # Compute pseudo-C_\ell
    cls = []
    for icl, i, j in man.cl_pair_iter(nmaps):
        f1 = fields[i]
        f2 = fields[j]
        pcl = binning.bin_cell(nmt.compute_coupled_cell(f1, f2))
        if winv is not None:
            pcl = np.dot(winv, pcl.flatten()).reshape([4, nbpw])
        cls.append(pcl)

    # Save to sacc
    leff = binning.get_effective_ells()
    s = sacc.Sacc()
    for n in names:
        s.add_tracer('Misc', n)
    for icl, i, j in man.cl_pair_iter(nmaps):
        s.add_ell_cl('cl_ee', names[i], names[j], leff, cls[icl][0])
        s.add_ell_cl('cl_eb', names[i], names[j], leff, cls[icl][1])
        if i != j:
            s.add_ell_cl('cl_be', names[i], names[j], leff, cls[icl][2])
        s.add_ell_cl('cl_bb', names[i], names[j], leff, cls[icl][3])
    s.save_fits(fname_out, overwrite=True)


def beam_gaussian(ll, fwhm_amin):
    """
    Returns the SHT of a Gaussian beam.
    Args:
        l (float or array): multipoles.
        fwhm_amin (float): full-widht half-max in arcmins.
    Returns:
        float or array: beam sampled at `l`.
    """
    sigma_rad = np.radians(fwhm_amin / 2.355 / 60)
    return np.exp(-0.5 * ll * (ll + 1) * sigma_rad**2)


def beam_hpix(ll, nside):
    """
    Returns the SHT of the beam associated with a HEALPix
    pixel size.
    Args:
        l (float or array): multipoles.
        nside (int): HEALPix resolution parameter.
    Returns:
        float or array: beam sampled at `l`.
    """
    fwhm_hp_amin = 60 * 41.7 / nside
    return beam_gaussian(ll, fwhm_hp_amin)


class PipelineManager(object):
    def __init__(self, fname_config):
        with open(fname_config) as f:
            self.config = yaml.load(f, Loader=yaml.FullLoader)
        self.nside = self.config['nside']
        self.fname_mask = self.config['mask']
        self.fname_binary_mask = self.config['binary_mask']
        self.bpw_edges = None
        self.pl_names = np.loadtxt(self.config['pl_sims'], dtype=str)
        self.val_names = np.loadtxt(self.config['val_sims'], dtype=str)
        self.pl_input_dir = self.config['pl_sims_dir']
        self.val_input_dir = self.config['val_sims_dir']
        self._get_cls_PL()
        self._get_cls_val()

        self.stname_mcm = 'mcm'
        self.stname_filtpl = 'filter_PL'
        self.stname_pclpl_in = 'pcl_PL_in'
        self.stname_pclpl_filt = 'pcl_PL_filt'
        self.stname_filtval = 'filter_val'
        self.stname_pclval_in = 'pcl_val_in'
        self.stname_pclval_filt = 'pcl_val_filt'
        self.stname_clval = 'cl_val'
        self.stname_transfer = 'transfer'

    def get_filename(self, product, out_base_dir, simname=None):
        if product == 'mcm':  # NaMaster's MCM
            fname = os.path.join(out_base_dir, '..',
                                 self.stname_mcm, 'mcm.npz')
        if product == 'mcm_plots':  # NaMaster's MCM plots dir
            fname = os.path.join(out_base_dir, '..',
                                 self.stname_mcm)
        if product == 'pl_sim_input':  # Input PL sims
            fname = os.path.join(self.pl_input_dir,
                                 simname+'.fits')
        if product == 'pl_sim_filtered':  # Filtered PL sims
            fname = os.path.join(
                out_base_dir, '..', self.stname_filtpl,
                simname+'.fits')
        if product == 'pcl_pl_sim_input':  # PCL of input PL sims
            fname = os.path.join(
                out_base_dir, '..', self.stname_pclpl_in,
                simname+'_pcl_in.fits')
        if product == 'pcl_pl_sim_filtered':  # PCL of filtered PL sims
            fname = os.path.join(
                out_base_dir, '..', self.stname_pclpl_filt,
                simname+'_pcl_filt.fits')
        if product == 'val_sim_input':  # Input validation sims
            fname = os.path.join(self.val_input_dir,
                                 simname+'.fits')
        if product == 'val_sim_filtered':  # Filtered validation sims
            fname = os.path.join(
                out_base_dir, '..', self.stname_filtval,
                simname+'.fits')
        if product == 'pcl_val_sim_input':  # PCL of input validations sims
            fname = os.path.join(
                out_base_dir, '..', self.stname_pclval_in,
                simname+'_pcl_in.fits')
        if product == 'pcl_val_sim_filtered':  # PCL of filtered validation sims
            fname = os.path.join(
                out_base_dir, '..', self.stname_pclval_filt,
                simname+'_pcl_filt.fits')
        if product == 'cl_val_sim':  # CL of filtered validation sims
            fname = os.path.join(
                out_base_dir, '..', self.stname_clval,
                simname+'_cl.fits')
        if product == 'transfer_function':
            fname = os.path.join(
                out_base_dir, '..', self.stname_transfer, 'transfer.npz')
        return fname

    def _get_cls_PL(self):
        d = np.load(self.config['cl_PL'])
        lin = d['ls']
        ls = np.arange(3*self.nside)
        self.cls_PL = []
        for kind in ['EE', 'EB', 'BE', 'BB']:
            cli = interp1d(lin, d[f'cl{kind}'], bounds_error=False,
                           fill_value=0)
            self.cls_PL.append(cli(ls))
        self.cls_PL = np.array(self.cls_PL)

    def _get_cls_val(self):
        d = np.load(self.config['cl_val'])
        lin = d['ls']
        ls = np.arange(3*self.nside)
        self.cls_val = []
        for kind in ['EE', 'EB', 'BE', 'BB']:
            cli = interp1d(lin, d[f'cl{kind}'], bounds_error=False,
                           fill_value=0)
            self.cls_val.append(cli(ls))
        self.cls_val = np.array(self.cls_val)

    def get_bpw_edges(self):
        if self.bpw_edges is None:
            self.bpw_edges = np.load(self.config['bpw_edges'])['bpw_edges']
        return self.bpw_edges

    def get_nmt_bins(self):
        bpw_edges = self.get_bpw_edges()
        b = nmt.NmtBin.from_edges(bpw_edges[:-1], bpw_edges[1:])
        return b

    def cl_pair_iter(self, nmaps):
        icl = 0
        for i in range(nmaps):
            for j in range(i, nmaps):
                yield icl, i, j
                icl += 1

    def val_sim_names(self, sim0, nsims, output_dir, which='input'):
        if nsims == -1:
            names = self.val_names[sim0:]
        else:
            names = self.val_names[sim0:sim0+nsims]
        fnames = []
        for n in names:
            if which == 'names':
                fn = n
            elif which == 'input':
                fn = self.get_filename('val_sim_input',
                                       output_dir, n)
            elif which in ['filtered', 'decoupled']:
                fn = self.get_filename('val_sim_filtered',
                                       output_dir, n)
            elif which == 'input_Cl':
                fn = self.get_filename("pcl_val_sim_input",
                                       output_dir, n)
            elif which == 'filtered_Cl':
                fn = self.get_filename("pcl_val_sim_filtered",
                                       output_dir, n)
            elif which == 'decoupled_Cl':
                fn = self.get_filename("cl_val_sim",
                                       output_dir, n)
            else:
                raise ValueError(f"Unknown kind {which}")
            fnames.append(fn)
        return fnames

    def pl_sim_names_EandB(self, sim0, nsims, output_dir, which):
        return self.pl_sim_names(sim0, nsims, output_dir,
                                 which=which, EandB=True)

    def pl_sim_names(self, sim0, nsims, output_dir, which='input',
                     EandB=False):
        if nsims == -1:
            names = self.pl_names[sim0:]
        else:
            names = self.pl_names[sim0:sim0+nsims]
        fnames = []
        for n in names:
            if which == 'names':
                fE = n+'_E'
                fB = n+'_B'
                if EandB:
                    fnames.append([fE, fB])
                else:
                    fnames.append(fE)
                    fnames.append(fB)
            elif which == 'input':
                fE = self.get_filename('pl_sim_input',
                                       output_dir, n+'_E')
                fB = self.get_filename('pl_sim_input',
                                       output_dir, n+'_B')
                if EandB:
                    fnames.append([fE, fB])
                else:
                    fnames.append(fE)
                    fnames.append(fB)
            elif which == 'filtered':
                fE = self.get_filename('pl_sim_filtered',
                                       output_dir, n+'_E')
                fB = self.get_filename('pl_sim_filtered',
                                       output_dir, n+'_B')
                if EandB:
                    fnames.append([fE, fB])
                else:
                    fnames.append(fE)
                    fnames.append(fB)
            elif which == 'input_Cl':
                fn = self.get_filename('pcl_pl_sim_input', output_dir, n)
                fnames.append(fn)
            elif which == 'filtered_Cl':
                fn = self.get_filename('pcl_pl_sim_filtered', output_dir, n)
                fnames.append(fn)
            else:
                raise ValueError(f"Unknown kind {which}")
        return fnames
