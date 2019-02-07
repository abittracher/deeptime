import numpy as np

from sktime.base import Estimator
from .util.running_moments import running_covar as running_covar

__all__ = ['OnlineCovariance']

__author__ = 'paul, nueske, marscher, clonker'


class OnlineCovarianceModel(object):
    def __init__(self):
        self._cov_00 = None
        self._cov_0t = None
        self._cov_tt = None
        self._mean_0 = None
        self._mean_t = None

    @property
    def cov_00(self):
        return self._cov_00

    @property
    def cov_0t(self):
        return self._cov_0t

    @property
    def cov_tt(self):
        return self._cov_tt

    @property
    def mean_0(self):
        return self._mean_0

    @property
    def mean_t(self):
        return self._mean_t


class OnlineCovariance(Estimator):
    r"""Compute (potentially lagged) covariances between data in an online fashion.

     Parameters
     ----------
     c00 : bool, optional, default=True
         compute instantaneous correlations over the first part of the data. If lag==0, use all of the data.
         Makes the C00_ attribute available.
     c0t : bool, optional, default=False
         compute lagged correlations. Does not work with lag==0.
         Makes the C0t_ attribute available.
     ctt : bool, optional, default=False
         compute instantaneous correlations over the time-shifted chunks of the data. Does not work with lag==0.
         Makes the Ctt_ attribute available.
     remove_data_mean : bool, optional, default=False
         subtract the sample mean from the time series (mean-free correlations).
     reversible : bool, optional, default=False
         symmetrize correlations.
     bessel : bool, optional, default=True
         use Bessel's correction for correlations in order to use an unbiased estimator
     sparse_mode : str, optional, default='auto'
         one of:
             * 'dense' : always use dense mode
             * 'auto' : automatic
             * 'sparse' : always use sparse mode if possible
     lagtime: int, optional, default=0
         lag time. Does not work with c0t=True or ctt=True.
     column_selection: ndarray(k, dtype=int) or None
         Indices of those columns that are to be computed. If None, all columns are computed.
     diag_only: bool
         If True, the computation is restricted to the diagonal entries (autocorrelations) only.
     """

    def __init__(self, compute_c00=True, compute_c0t=False, compute_ctt=False, remove_data_mean=False,
                 reversible=False, bessel=True, sparse_mode='auto', ncov=5, diag_only=False, model=None):
        super(OnlineCovariance, self).__init__(model=model)

        if diag_only and sparse_mode is not 'dense':
            if sparse_mode is 'sparse':
                import warnings
                warnings.warn('Computing diagonal entries only is not implemented for sparse mode. Switching to dense '
                              'mode.')
            sparse_mode = 'dense'

        self.compute_c00 = compute_c00
        self.compute_c0t = compute_c0t
        self.compute_ctt = compute_ctt
        self.remove_data_mean = remove_data_mean
        self.reversible = reversible
        self.bessel = bessel
        self.sparse_mode = sparse_mode
        self.ncov = ncov
        self.diag_only = diag_only

        self._rc = running_covar(xx=self.compute_c00, xy=self.compute_c0t, yy=self.compute_ctt,
                                 remove_mean=self.remove_data_mean, symmetrize=self.reversible,
                                 sparse_mode=self.sparse_mode, modify_data=False, diag_only=self.diag_only,
                                 nsave=ncov)

    def _create_model(self):
        return OnlineCovarianceModel()

    @property
    def is_lagged(self) -> bool:
        return self.compute_c0t or self.compute_ctt

    def fit(self, data, weights=None, n_splits=None, column_selection=None):
        self._rc.clear()
        if n_splits is None:
            if self.is_lagged:
                dlen = len(data[0])
            else:
                dlen = len(data)
            n_splits = int(dlen // 100 if dlen >= 1e4 else 1)
        if self.is_lagged:
            if not (isinstance(data, (list, tuple)) and len(data) == 2 and len(data[0]) == len(data[1])):
                raise ValueError("Expected tuple of arrays of equal length!")
            x, x_lagged = data
        else:
            x, x_lagged = data, np.array([], dtype=data.dtype)

        if weights is not None and len(np.atleast_1d(weights)) != len(x):
            raise ValueError("Weights have incompatible shape.")
        wsplit = np.array_split(weights, n_splits) if weights is not None else [None] * n_splits

        for x_batch, y_batch, w in zip(np.array_split(x, n_splits), np.array_split(x_lagged, n_splits), wsplit):
            assert len(x_batch) == len(y_batch) or (not self.is_lagged and len(y_batch) == 0)
            self.partial_fit((x_batch, y_batch), column_selection=column_selection, weights=w)

        return self

    def partial_fit(self, data, weights=None, column_selection=None):
        """ incrementally update the estimates

        Parameters
        ----------
        data: array, list of arrays, PyEMMA reader
            input data.
        column_selection: foo
        """
        if self.is_lagged:
            x, y = data
        else:
            x, y = data, tuple()
        if weights is not None and len(x) != len(np.atleast_1d(weights)):
            raise ValueError("Weights have incompatible ")
        try:
            self._rc.add(x, y if len(y) > 0 else None, column_selection=column_selection, weights=weights)
        except MemoryError:
            raise MemoryError('Covariance matrix does not fit into memory. '
                              'Input is too high-dimensional ({} dimensions). '.format(x.shape[1]))
        return self

    def _update_model(self):
        if self.compute_c0t:
            self._model._cov_0t = self._rc.cov_XY(self.bessel)
        if self.compute_ctt:
            self._model._cov_tt = self._rc.cov_YY(self.bessel)
        if self.compute_c00:
            self._model._cov_00 = self._rc.cov_XX(self.bessel)

        if self.compute_c00 or self.compute_c0t:
            self._model._mean_0 = self._rc.mean_X()
        if self.compute_ctt or self.compute_c0t:
            self._model._mean_t = self._rc.mean_Y()

    @property
    def model(self):
        self._update_model()
        return self._model
