"""
pysteps.cascade.decomposition
=============================

Methods for decomposing two-dimensional fields into multiple spatial scales and
recomposing the individual scales back to the original field.

The methods in this module implement the following interface::

    decomposition_xxx(field, bp_filter, **kwargs)
    recompose_xxx(decomp, **kwargs)

where field is the input field and bp_filter is a dictionary returned by a
filter method implemented in :py:mod:`pysteps.cascade.bandpass_filters`. The
decomp argument is a decomposition obtained by calling decomposition_xxx.
Optional parameters can be passed in
the keyword arguments. The output of each method is a dictionary with the
following key-value pairs:

+-------------------+----------------------------------------------------------+
|        Key        |                      Value                               |
+===================+==========================================================+
|  cascade_levels   | three-dimensional array of shape (k,m,n), where k is the |
|                   | number of cascade levels and the input fields have shape |
|                   | (m,n)                                                    |
+-------------------+----------------------------------------------------------+

Available methods
-----------------

.. autosummary::
    :toctree: ../generated/

    decomposition_fft
    recompose_fft
"""

import numpy as np
from pysteps import utils


def decomposition_fft(field, bp_filter, **kwargs):
    """Decompose a two-dimensional input field into multiple spatial scales by
    using the Fast Fourier Transform (FFT) and a set of bandpass filters.

    Parameters
    ----------
    field : array_like
        Two-dimensional array containing the input field. All values are
        required to be finite.
    bp_filter : dict
        A filter returned by a method implemented in
        :py:mod:`pysteps.cascade.bandpass_filters`.

    Other Parameters
    ----------------
    fft_method : str or tuple
        A string or a (function,kwargs) tuple defining the FFT method to use
        (see :py:func:`pysteps.utils.interface.get_method`).
        Defaults to "numpy". This option is not used if input_domain and
        output_domain are both set to "spectral".
    normalize : bool
        If True, normalize the cascade levels to zero mean and unit variance.
        Requires that compute_stats is True.
    MASK : array_like
        Optional mask to use for computing the statistics for the cascade
        levels. Pixels with MASK==False are excluded from the computations.
        This option is not used if output domain is "spectral".
    input_domain : {"spatial", "spectral"}
        The domain of the input field. If "spectral", the input is assumed to
        be in the spectral domain. Defaults to "spatial".
    output_domain : {"spatial", "spectral"}
        If "spatial", the output cascade levels are transformed back to the
        spatial domain by using the inverse FFT. If "spectral", the cascade is
        kept in the spectral domain. Defaults to "spatial".
    compute_stats : bool
        If True, the output dictionary contains the keys "means" and "stds"
        for the mean and standard deviation of each output cascade level.
        Defaults to False.
    compact_output : bool
        Applicable if output_domain is "spectral". If set to True, only the
        parts of the Fourier spectrum with nonzero filter weights are stored.
        Defaults to False.

    Returns
    -------
    out : ndarray
        A dictionary described in the module documentation.
        The number of cascade levels is determined from the filter
        (see :py:mod:`pysteps.cascade.bandpass_filters`).

    """
    fft = kwargs.get("fft_method", "numpy")
    if isinstance(fft, str):
        fft = utils.get_method(fft, shape=field.shape)
    normalize = kwargs.get("normalize", False)
    mask = kwargs.get("MASK", None)
    input_domain = kwargs.get("input_domain", "spatial")
    output_domain = kwargs.get("output_domain", "spatial")
    compute_stats = kwargs.get("compute_stats", False)
    compact_output = kwargs.get("compact_output", True)

    if normalize and not compute_stats:
        raise ValueError("incorrect input arguments: normalization=True but compute_stats=False")

    if len(field.shape) != 2:
        raise ValueError("The input is not two-dimensional array")

    if mask is not None and mask.shape != field.shape:
        raise ValueError("Dimension mismatch between field and MASK:"
                         + "field.shape=" + str(field.shape)
                         + ",mask.shape" + str(mask.shape))

    if field.shape[0] != bp_filter["weights_2d"].shape[1]:
        raise ValueError(
            "dimension mismatch between field and bp_filter: "
            + "field.shape[0]=%d , " % field.shape[0]
            + "bp_filter['weights_2d'].shape[1]"
              "=%d" % bp_filter["weights_2d"].shape[1])

    if input_domain == "spatial" and \
       int(field.shape[1] / 2) + 1 != bp_filter["weights_2d"].shape[2]:
        raise ValueError(
            "Dimension mismatch between field and bp_filter: "
            "int(field.shape[1]/2)+1=%d , " % (int(field.shape[1] / 2) + 1)
            + "bp_filter['weights_2d'].shape[2]"
              "=%d" % bp_filter["weights_2d"].shape[2])

    if input_domain == "spectral" and \
       field.shape[1] != bp_filter["weights_2d"].shape[2]:
        raise ValueError(
            "Dimension mismatch between field and bp_filter: "
            "field.shape[1]=%d , " % (field.shape[1] + 1)
            + "bp_filter['weights_2d'].shape[2]"
              "=%d" % bp_filter["weights_2d"].shape[2])

    if np.any(~np.isfinite(field)):
        raise ValueError("field contains non-finite values")

    result = {}
    means = []
    stds = []

    if input_domain == "spatial":
        field_fft = fft.rfft2(field)
    else:
        field_fft = field
        if compact_output:
            weight_masks = []
    field_decomp = []

    for k in range(len(bp_filter["weights_1d"])):
        field_ = field_fft * bp_filter["weights_2d"][k, :, :]

        if output_domain == "spatial" or (compute_stats and mask is not None):
            field__ = fft.irfft2(field_)
        else:
            field__ = field_

        if compute_stats:
            if output_domain == "spatial" or (compute_stats and mask is not None):
                if mask is not None:
                    masked_field = field__[mask]
                else:
                    masked_field = field__
                mean = np.mean(masked_field)
                std = np.std(masked_field)
            else:
                mean = utils.spectral.mean(field_, bp_filter["shape"])
                std = utils.spectral.std(field_, bp_filter["shape"])
            
            means.append(mean)
            stds.append(std)

        if output_domain == "spatial":
            if normalize:
                field__ = (field__ - mean) / std
            field_decomp.append(field__)
        else:
            weight_mask = bp_filter["weights_2d"][k, :, :] > 1e-4
            if compact_output:
                field_ = field_[weight_mask]
            if normalize:
                field_ = (field_ - mean) / std
            field_decomp.append(field_)
            if compact_output:
                weight_masks.append(weight_mask)

    result["domain"] = output_domain

    if output_domain == "spatial":
        field_decomp = np.stack(field_decomp)

    result["cascade_levels"] = field_decomp
    if output_domain == "spectral" and compact_output:
        result["weight_masks"] = np.stack(weight_masks)

    if compute_stats:
        result["means"] = means
        result["stds"] = stds

    return result


def recompose_fft(decomp, **kwargs):
    """Recompose a cascade obtained with decomposition_fft by inverting the
    normalization and summing the individual levels.

    Parameters
    ----------
    decomp : dict
        A cascade decomposition returned by decomposition_fft.
    
    Returns
    -------
    out : numpy.ndarray
        The recomposed cascade.
    """
    if not "means" in decomp.keys() or not "stds" in decomp.keys():
        raise KeyError("the decomposition was done with compute_stats=False")

    levels = decomp["cascade_levels"]
    mu = decomp["means"]
    sigma = decomp["stds"]

    if decomp["domain"] == "spatial":
        result = [levels[i, :, :] * sigma[i] + mu[i] for i in range(levels.shape[0])]

        return np.sum(np.stack(result), axis=0)
    else:
        weight_masks = decomp["weight_masks"]
        result = np.zeros(weight_masks.shape[1:], dtype=complex)

        for i in range(weight_masks.shape[0]):
            result[weight_masks[i]] += levels[i][weight_masks[i]] * sigma[i] + mu[i]

        return result
