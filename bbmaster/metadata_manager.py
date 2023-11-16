import yaml
import numpy as np
import os
import pymaster as nmt
import healpy as hp
from itertools import combinations_with_replacement as cwr

class BBmeta(object):
    """
    Metadata manager for the BBmaster pipeline.
    The purpose of this class is to provide
    a single interface to all the parameters and products
    that will be used from different stages of the pipeline.
    """


    def __init__(self, fname_config):
        """
        Initialize the pipeline manager from a yaml file.
        
        Parameters
        ----------
        fname_config : str
            Path to the yaml file with the configuration.
        """

        # Load the configuration file
        with open(fname_config) as f:
            self.config = yaml.load(f, Loader=yaml.FullLoader)

        # Set the high-level parameters as attributes
        for key in self.config:
            setattr(self, key, self.config[key])
        
        # Set all the `_directory` attributes
        self._set_directory_attributes()

        # Set the general attributes (nside, lmax, etc...)
        self._set_general_attributes()

        # Basic sanity checks
        if self.lmax > 3*self.nside-1:
            raise ValueError(f"lmax should be lower or equal to 3*nside-1 = {3*self.nside-1}")

        # Path to binning
        self.path_to_binning = f"{self.pre_process_directory}/{self.binning_file}"

        # Initialize method to parse map_sets metadata
        map_sets_attributes = list(self.map_sets[next(iter(self.map_sets))].keys())
        for map_sets_attribute in map_sets_attributes:
            self._init_getter_from_map_set(map_sets_attribute)

        # A list of the maps used in the analysis
        self.map_sets_list = self._get_map_sets_list()
        self.maps_list = self._get_map_list()

        # Initialize masks file_names
        for mask_type in ["binary", "galactic", "point_source", "analysis"]:
            setattr(
                self,
                f"{mask_type}_mask_name", 
                getattr(self, f"_get_{mask_type}_mask_name")()
            )

        # Simulation
        self._init_simulation_params()

        # Tf estimation 
        self._init_tf_estimation_params()
        self.tf_est_sims_dir = f"{self.pre_process_directory}/tf_est_sims"
        self.tf_val_sims_dir = f"{self.pre_process_directory}/tf_val_sims"
        self.cosmo_sims_dir = f"{self.pre_process_directory}/cosmo_sims"

        # Fiducial cls
        self.cosmo_cls_file = f"{self.pre_process_directory}/cosmo_cls.npz"
        self.tf_est_cls_file = f"{self.pre_process_directory}/tf_est_cls.npz"
        self.tf_val_cls_file = f"{self.pre_process_directory}/tf_val_cls.npz"


    def _set_directory_attributes(self):
        """
        Set the directory attributes that are listed
        in the paramfiles
        """
        for label, path in self.data_dirs.items():
            if label == "root": 
                self.data_dir = self.data_dirs["root"]
            else:
                full_path = f"{self.data_dirs['root']}/{path}"
                setattr(self, label, full_path)
                setattr(self, f"{label}_relative", path)
                os.makedirs(full_path, exist_ok=True)

        for label, path in self.output_dirs.items():
            if label == "root": 
                self.output_dir = self.output_dirs["root"]
            else:
                full_path = f"{self.output_dirs['root']}/{path}"
                setattr(self, label, full_path)
                setattr(self, f"{label}_relative", path)
                os.makedirs(full_path, exist_ok=True)
    
    def _set_general_attributes(self):
        """
        """
        for key, value in self.general_pars.items():
            setattr(self, key, value)


    def _get_map_sets_list(self):
        """
        List the different map set.
        Constructor for the map_sets_list attribute.
        """
        return list(self.map_sets.keys())
    
    
    def _get_map_list(self):
        """
        List the different maps (including splits).
        Constructor for the map_list attribute.
        """
        out_list = [
            f"{map_set}__{id_split}" for map_set in self.map_sets_list
                for id_split in range(self.n_splits_from_map_set(map_set))
        ]
        return out_list


    def _init_getter_from_map_set(self, map_set_attribute):
        """
        Initialize a getter for a map_set attribute.

        Parameters
        ----------
        map_set_attribute : str
            Should a key of the map_set dictionnary.
        """
        setattr(
            self,
            f"{map_set_attribute}_from_map_set",
            lambda map_set: self.map_sets[map_set][map_set_attribute]
        )


    def _get_galactic_mask_name(self):
        """
        Get the name of the galactic mask.
        """
        fname = f"{self.masks['galactic_mask_root']}_{self.masks['gal_mask_mode']}.fits"
        return os.path.join(self.mask_directory, fname)


    def _get_binary_mask_name(self):
        """
        Get the name of the binary or survey mask.
        """
        return os.path.join(self.mask_directory, self.masks["binary_mask"])


    def _get_point_source_mask_name(self):
        """
        Get the name of the point source mask.
        """
        return os.path.join(self.mask_directory, self.masks["point_source_mask"])


    def _get_analysis_mask_name(self):
        """
        Get the name of the final analysis mask.
        """
        return os.path.join(self.mask_directory, self.masks["analysis_mask"])

    

    def read_mask(self, mask_type):
        """
        Read the mask given a mask type.

        Parameters
        ----------
        mask_type : str
            Type of mask to load.
            Can be "binary", "galactic", "point_source" or "analysis".
        """
        return hp.read_map(getattr(self, f"{mask_type}_mask_name"))


    def save_mask(self, mask_type, mask, overwrite=False):
        """
        Save the mask given a mask type.

        Parameters
        ----------
        mask_type : str
            Type of mask to load.
            Can be "binary", "galactic", "point_source" or "analysis".
        mask : array-like
            Mask to save.
        overwrite : bool, optional
            Overwrite the mask if it already exists.
        """
        return hp.write_map(getattr(self, f"{mask_type}_mask_name"), mask, 
                            overwrite=overwrite)


    def read_hitmap(self):
        """
        Read the hitmap. For now, we assume that all tags
        share the same hitmap.
        """
        hitmap = hp.read_map(self.hitmap_file)
        return hp.ud_grade(hitmap, self.nside, power=-2)


    def read_nmt_binning(self):
        """
        Read the binning file and return the corresponding NmtBin object.
        """
        binning = np.load(self.path_to_binning)
        return nmt.NmtBin.from_edges(binning["bin_low"], binning["bin_high"] + 1)

    
    def get_n_bandpowers(self):
        """
        Read the binning file and return the number of ell-bins.
        """
        binner = self.read_nmt_binning()
        return binner.get_n_bands()
    
    
    def get_effective_ells(self):
        """
        Read the binning file and return the number of ell-bins.
        """
        binner = self.read_nmt_binning()
        return binner.get_effective_ells()

    def read_beam(self, map_set):
        """
        """
        file_root = self.file_root_from_map_set(map_set)
        beam_file = f"{self.beam_directory}/beam_{file_root}.dat"
        l, bl = np.loadtxt(beam_file, unpack=True)
        return l, bl
    

    def _init_simulation_params(self):
        """
        Loop over the simulation parameters and set them as attributes.
        """
        for name in ["num_sims", "cosmology",
                     "mock_nsrcs", "mock_srcs_hole_radius",
                     "hitmap_file"]:
            setattr(self, name, self.sim_pars[name])


    def _init_tf_estimation_params(self):
        """
        Loop over the transfer function parameters and set them as attributes.
        """
        for name in self.tf_settings:
            setattr(self, name, self.tf_settings[name])


    def save_fiducial_cl(self, l, cl_dict, cl_type):
        """
        Save a fiducial power spectra dictionnary to disk.

        Parameters
        ----------
        l : array-like
            Multipole values.
        cl_dict : dict
            Dictionnary with the power spectra.
        cl_type : str
            Type of power spectra.
            Can be "cosmo", "tf_est" or "tf_val".
        """
        fname = getattr(self, f"{cl_type}_cls_file")
        np.savez(fname, l=l, **cl_dict)


    def load_fiducial_cl(self, cl_type):
        """
        Load a fiducial power spectra dictionary from disk.

        Parameters
        ----------
        cl_type : str
            Type of power spectra.
            Can be "cosmo", "tf_est" or "tf_val".
        """
        fname = getattr(self, f"{cl_type}_cls_file")
        return np.load(fname)
    

    def plot_dir_from_output_dir(self, out_dir):
        """
        """
        root = self.output_dir

        if root in out_dir:
            path_to_plots = out_dir.replace(f"{root}/", f"{root}/plots/")
        else:
            path_to_plots = f"{root}/plots/{out_dir}"

        os.makedirs(path_to_plots, exist_ok=True)

        return path_to_plots


    def get_fname_mask(self, map_type='analysis'):
        """
        Get the full filepath to a mask of predefined type.
        
        Parameters
        ----------
        map_type : str
            Choose between 'analysis', 'binary', 'point_source'.
            Defaults to 'analysis'.
        """
        base_dir = self.masks['mask_directory']
        if map_type=='analysis':
            fname = os.path.join(base_dir, self.masks['analysis_mask'])
        elif map_type=='binary':
            fname = os.path.join(base_dir, self.masks['binary_mask'])
        elif map_type=='point_source':
            fname = os.path.join(base_dir, self.masks['point_source_mask'])
        else:
            raise ValueError("The map_type chosen does not exits. "
                             "Choose between 'analysis', 'binary', "
                             "'point_source'.")
        return fname
    

    def get_map_filename(self, map_set, id_split, id_sim=None):
        """
        Get the path to file for a given `map_set` and split index.
        Can also get the path to a given simulation if `id_sim` is provided.

        Path to standard map : {map_directory}/{map_set_root}_split_{id_split}.fits
        Path to sim map : e.g. {sims_directory}/0000/{map_set_root}_split_{id_split}.fits

        Parameters
        ----------
        map_set : str
            Name of the map set.
        id_split : int
            Index of the split.
        id_sim : int, optional
            Index of the simulation.
            If None, return the path to the data map.
        """
        map_set_root = self.file_root_from_map_set(map_set)
        if id_sim is not None:
            path_to_maps = os.path.join(
                self.sims_directory,
                f"{id_sim:04d}"
            )
            os.makedirs(path_to_maps, exist_ok=True)
        else:
            path_to_maps = self.map_directory
        
        return os.path.join(path_to_maps, f"{map_set_root}_split_{id_split}.fits")


    def get_map_filename_transfer2(self, id_sim, cl_type, pure_type=None):
        """
        """
        path_to_maps = getattr(self, f"{cl_type}_sims_dir")

        pure_label = f"_{pure_type}" if pure_type else ""
        file_name = f"TQU{pure_label}_noiseless_nside{self.nside}_lmax{self.lmax}_{id_sim:04d}.fits"

        return f"{path_to_maps}/{file_name}"


    def get_map_filename_transfer(id_sim, signal=None, e_or_b=None):
        """
        Get the path to transfer function simulation or validation map for a 
        given simulation index. Choosing either a signal or polarization type 
        defines what type is loaded.

        Path to simulation map: e.g. {sims_directory}/0000/{map_set_root}_pure{e_or_b}.fits
        Path to validation map: e.g. {sims_directory}/0000/{map_set_root}_{signal}.fits

        Parameters
        ----------
        id_sim : int
            Index of the simulation.
            If None, return the path to the data map.
        signal : str, optional
            Determines what signal the validation map corresponds to.
            If None, assumes simulation mode.
        e_or_b : str, optional
            Accepts either `E`, `B`, or None. Determines what pure-polarization
            type (E or B) the map corresponds to. 
            If None, assumes validation mode.
        """
        
        os.makedirs(path_to_maps, exist_ok=True)
        if (not signal and not e_or_b) or (signal and e_or_b):
            raise ValueError("You have to set to None either `signal` or "
                             "`e_or_b`")
        if signal is not None:
            fname = os.path.join(
                self.sim_pars['transsims_directory'],
                f"{id_sim:04d}", 
                f"pure{e_or_b}.fits"
            )
        else:
            fname = os.path.join(
                self.sim_pars['transval_directory'],
                f"{id_sim:04d}", 
                f"{signal}.fits"
            )
        return fname
        
    
    def read_map(self, map_set, id_split, id_sim=None, pol_only=False):
        """
        Read a map given a map set and split index.
        Can also read a given covariance simulation if `id_sim` is provided.

        Parameters
        ----------
        map_set : str
            Name of the map set.
        id_split : int
            Index of the split.
        id_sim : int, optional
            Index of the simulation.
            If None, return the data map.
        pol_only : bool, optional
            Return only the polarization maps.
        """
        field = [1, 2] if pol_only else [0, 1, 2]
        fname = self.get_map_filename(map_set, id_split, id_sim)
        return hp.read_map(fname, field=field)
    
    
    def read_map_transfer(self, id_sim, signal=None, e_or_b=None, 
                          pol_only=False):
        """
        Read a map given a simulation index.
        Can also read a pure-E or pure-B simulation if `e_or_b` is provided.

        Parameters
        ----------
        id_sim : int
            Index of the simulation.
        signal : str, optional
            Determines what signal the validation map corresponds to. For now, 
            available choices are 'CMB' and 'dust'. 
            If None, assumes simulation mode.
        e_or_b : str
            Accepts either `E`, `B`, or None. Determines what pure-polarization
            type (E or B) the map corresponds to. 
            If None, assumes validation mode.
        pol_only : bool, optional
            Return only the polarization maps.
        """
        field = [1, 2] if pol_only else [0, 1, 2]
        if (not signal and not e_or_b) or (signal and e_or_b):
            raise ValueError("You have to set to None either `signal` or "
                             "`e_or_b`")
        fname = self.get_map_filename_transfer(id_sim, signal, e_or_b)
        return hp.read_map_transfer(fname, field=field)
    
    
    def get_ps_names_list(self, type="all", coadd=False):
        """
        List all the possible cross split power spectra
        Example: 
            From two map_sets `ms1` and `ms2` with
            two splits each, and `type="all"`, 
            this function will return :
            [('ms1__0', 'ms1__0'), ('ms1__0', 'ms1__1'),
             ('ms1__0', 'ms2__0'), ('ms1__0', 'ms2__1'),
             ('ms1__1', 'ms1__1'), ('ms1__1', 'ms2__0'),
             ('ms1__1', 'ms2__1'), ('ms2__0', 'ms2__0'),
             ('ms2__0', 'ms2__1'), ('ms2__1', 'ms2__1')]

        Parameters
        ----------
        type : str, optional
            Type of power spectra to return.
            Can be "all", "auto" or "cross".
        coadd: bool, optional
            If True, return the cross-split power spectra names.
            Else, return the (split-)coadded power spectra names.
        """
        map_iterable = self.map_sets_list if coadd else self.maps_list

        ps_name_list = []
        for i, map1 in enumerate(map_iterable):
            for j, map2 in enumerate(map_iterable):

                if coadd:
                    if i > j: continue
                    if (type == "cross") and (i == j): continue
                    if (type == "auto") and (i != j): continue

                else:
                    map_set_1, split_1 = map1.split("__")
                    map_set_2, split_2 = map2.split("__")

                    if (map_set_1 == map_set_2) and (split_1 > split_2): continue

                    exp_tag_1 = self.exp_tag_from_map_set(map_set_1)
                    exp_tag_2 = self.exp_tag_from_map_set(map_set_2)
                    if (type == "cross") and (exp_tag_1 == exp_tag_2) and (split_1 == split_2): continue
                    if (type == "auto") and (exp_tag_1 != exp_tag_2) and (split_1 != split_2): continue

                ps_name_list.append((map1, map2))
        return ps_name_list