"""
Module containing implementations of some unnormalized probability density 
functions.
"""

__author__ = 'wittawat'

from abc import ABCMeta, abstractmethod
import autograd
import autograd.numpy as np
import kgof.config as config
import kgof.util as util
import kgof.data as data
import scipy.stats as stats

class UnnormalizedDensity(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def log_den(self, X):
        """
        Evaluate this log of the unnormalized density on the n points in X.

        X: n x d numpy array

        Return a one-dimensional numpy array of length n.
        """
        raise NotImplementedError()

    def log_normalized_den(self, X):
        """
        Evaluate the exact normalized log density. The difference to log_den()
        is that this method adds the normalizer. This method is not
        compulsory. Subclasses do not need to override.
        """
        raise NotImplementedError()

    def get_datasource(self):
        """
        Return a DataSource that allows sampling from this density.
        May return None if no DataSource is implemented.
        Implementation of this method is not enforced in the subclasses.
        """
        return None

    def grad_log(self, X):
        """
        Evaluate the gradients (with respect to the input) of the log density at
        each of the n points in X. This is the score function. Given an
        implementation of log_den(), this method will automatically work.
        Subclasses may override this if a more efficient implementation is
        available.

        X: n x d numpy array.

        Return an n x d numpy array of gradients.
        """
        g = autograd.elementwise_grad(self.log_den)
        G = g(X)
        return G

    @abstractmethod
    def dim(self):
        """
        Return the dimension of the input.
        """
        raise NotImplementedError()

# end UnnormalizedDensity

class IsotropicNormal(UnnormalizedDensity):
    """
    Unnormalized density of an isotropic multivariate normal distribution.
    """
    def __init__(self, mean, variance):
        """
        mean: a numpy array of length d for the mean 
        variance: a positive floating-point number for the variance.
        """
        self.mean = mean 
        self.variance = variance

    def log_den(self, X):
        mean = self.mean 
        variance = self.variance
        unden = -np.sum((X-mean)**2, 1)/(2.0*variance)
        return unden

    def log_normalized_den(self, X):
        d = self.dim()
        return stats.multivariate_normal.logpdf(X, mean=self.mean, cov=self.variance*np.eye(d))

    def get_datasource(self):
        return data.DSIsotropicNormal(self.mean, self.variance)

    def dim(self):
        return len(self.mean)


class Normal(UnnormalizedDensity):
    """
    A multivariate normal distribution.
    """
    def __init__(self, mean, cov):
        """
        mean: a numpy array of length d.
        cov: d x d numpy array for the covariance.
        """
        self.mean = mean 
        self.cov = cov
        assert mean.shape[0] == cov.shape[0]
        assert cov.shape[0] == cov.shape[1]
        E, V = np.linalg.eig(cov)
        if np.any(np.abs(E) <= 1e-7):
            raise ValueError('covariance matrix is not full rank.')
        # The precision matrix
        self.prec = np.dot(np.dot(V, np.diag(1.0/E)), V.T)
        print self.prec

    def log_den(self, X):
        mean = self.mean 
        X0 = X - mean
        X0prec = np.dot(X0, self.prec)
        unden = -np.sum(X0prec*X0, 1)/2.0
        return unden

    def get_datasource(self):
        return data.DSNormal(self.mean, self.cov)

    def dim(self):
        return len(self.mean)


# end Normal

class GaussBernRBM(UnnormalizedDensity):
    """
    Gaussian-Bernoulli Restricted Boltzmann Machine.
    The joint density takes the form
        p(x, h) = Z^{-1} exp(0.5*x^T B h + b^T x + c^T h - 0.5||x||^2)
    where h is a vector of {-1, 1}.
    """
    def __init__(self, B, b, c):
        """
        B: a dx x dh matrix 
        b: a numpy array of length dx
        c: a numpy array of length dh
        """
        dh = len(c)
        dx = len(b)
        assert B.shape[0] == dx
        assert B.shape[1] == dh
        assert dx > 0
        assert dh > 0
        self.B = B
        self.b = b
        self.c = c

    def log_den(self, X):
        B = self.B
        b = self.b
        c = self.c

        XBC = np.dot(X, B) + c
        unden = np.dot(X, b) - 0.5*np.sum(X**2, 1) + np.sum(np.log(np.exp(XBC)
            + np.exp(-XBC)), 1)
        assert len(unden) == X.shape[0]
        return unden

    def grad_log(self, X):
        """
        Evaluate the gradients (with respect to the input) of the log density at
        each of the n points in X. This is the score function.

        X: n x d numpy array.

        Return an n x d numpy array of gradients.
        """
        XB = np.dot(X, self.B)
        Y = XB + self.c
        E2y = np.exp(2*Y)
        # n x dh
        Phi = (E2y-1.0)/(E2y+1)
        # n x dx
        T = np.dot(Phi, self.B.T)
        S = self.b - X + T
        return S

    def get_datasource(self):
        return data.DSGaussBernRBM(self.B, self.b, self.c)

    def dim(self):
        return len(self.b)

# end GaussBernRBM

class NonHomPoissonLinear(UnnormalizedDensity):
    """
    Unnormalized density of inter-arrival times from nonhomogeneous poisson process with linear intensity function.
    lambda = 1 + bt
    """
    def __init__(self, b):
        """
        b: slope of the linear function 
        """
        self.b = b 
    
    def log_den(self, X):
        b = self.b
        unden = -np.sum(0.5*b*X**2+X-np.log(1.0+b*X), 1)
        return unden

    def dim(self):
        return 1

# end NonHomPoissonLinear

class NonHomPoissonSine(UnnormalizedDensity):
    """
    Unnormalized density of inter-arrival times from nonhomogeneous poisson process with sine intensity function.
    lambda = b*(1+sin(w*X))
    """
    def __init__(self, w=10.0,b=1.0):
        """
        w: the frequency of sine function
        b: amplitude of intensity function
        """
        self.b = b
        self.w = w
    
    def log_den(self, X):
        b = self.b
        w = self.w
        unden = np.sum(b*(-X + (np.cos(w*X)-1)/w) + np.log(b*(1+np.sin(w*X))),1)
        return unden

    def dim(self):
        return 1

# end NonHomPoissonSine


class Gamma(UnnormalizedDensity):
    """
    A gamma distribution.
    """
    def __init__(self, alpha, beta = 1.0):
        """
        alpha: shape of parameter
        beta: scale
        """
        self.alpha = alpha 
        self.beta = beta
        
    def log_den(self, X):
        alpha = self.alpha
        beta = self.beta
        #unden = np.sum(stats.gamma.logpdf(X, alpha, scale = beta), 1)
        unden = np.sum(-beta*X + (alpha-1)*np.log(X), 1)
        return unden

    def get_datasource(self):
        return data.DSNormal(self.mean, self.cov)

    def dim(self):
        return 1


# end Normal


class LogGamma(UnnormalizedDensity):
    """
    A gamma distribution with transformed domain.
    t = exp(x),  t \in R+  x \in R
    """
    def __init__(self, alpha, beta = 1.0):
        """
        alpha: shape of parameter
        beta: scale
        """
        self.alpha = alpha
        self.beta = beta
        
    def log_den(self, X):
        alpha = self.alpha
        beta = self.beta
        #unden = np.sum(stats.gamma.logpdf(X, alpha, scale = beta), 1)
        unden = np.sum(-beta*np.exp(X) + (alpha-1)*X + X , 1)
        return unden

    def get_datasource(self):
        return data.DSNormal(self.mean, self.cov)

    def dim(self):
        return 1


# end Normal


class LogPoissonLinear(UnnormalizedDensity):
    """
    Unnormalized density of inter-arrival times from nonhomogeneous poisson process with linear intensity function.
    lambda = 1 + bt
    """
    def __init__(self, b):
        """
        b: slope of the linear function 
        """
        self.b = b 
    
    def log_den(self, X):
        b = self.b
        unden = -np.sum(0.5*b*np.exp(X)**2 + np.exp(X) - np.log(1.0+b*np.exp(X))-X, 1)
        return unden

    def dim(self):
        return 1

# end NonHomPoissonLinear