import numpy as np
from sklearn.metrics import pairwise_distances
from ...utils import generate_features, DataChecker


class STIR(DataChecker):
    """
        Feature selection using STIR algorithm.

        Algorithm taken from paper:

        STatistical Inference Relief (STIR) feature selection
        (https://academic.oup.com/bioinformatics/article/35/8/1358/5100883).
    """

    def __init__(self, n_features_to_keep=10):
        """
            Sets up STIR to perform feature selection.
        """

        self.n_features_to_keep = n_features_to_keep
        self.feature_scores = None
        self.top_features = None

    def max_diff(self, X):
        """
            Computes max difference in each column.

            Parameters
            ----------
            X : array-like, shape (n_samples, n_features) 
                matrix to compute column difference of.

            Returns
            -------
            diff_vector : array-like, shape (n_features)
                column difference vector.
        """

        diff_vector = np.max(X, axis=0) - np.min(X, axis=0)

        return diff_vector

    def distance_matrix(self, X):
        """
            Computes the distance matrix.

            Before calculating distance we center
            matrix and normalize it.

            Parameters
            ----------
            X : array-like, shape (n_samples, n_features) 
                matrix to compute column difference of.

            Returns
            -------
            X_distances : array-like, shape (n_samples, n_samples)
                distance matrix.
        """

        #max_diff_vec = self.max_diff(X) # TODO: probably should convert to float64 and add division by zero check
        max_diff_vec = self.max_diff(X).astype('float64')
        min_vec = X.min(axis=0)

        X_centered = X - min_vec
        max_diff_vec[max_diff_vec == 0] = 1e-14
        X_scaled = X_centered / max_diff_vec
        X_distances = pairwise_distances(X_scaled)

        return X_distances

    def find_neighbors(self, X, y, k=1):
        """
            Finds the nearest hit/miss matrices.

            Parameters
            ----------
            X : array-like, shape (n_samples, n_features)
                matrix to compute neighbors of.
            y : array-like, shape (n_samples, )
                vector of binary class status (usually -1/1).
            k : int, optional
                number of constant nearest hits/misses.

            Returns
            -------
            hitmiss : array-like, shape (2, )
                hitmiss[1] (hits) and hitmiss[2] (misses). 
                Each list has two columns: index is the first column (instances) 
                in both lists. The second column is hit_index (nearest hits for 
                the first column instance) for list [1] and miss_index 
                (nearest misses) for list [2].
        """

        X_distances = self.distance_matrix(X)
        num_samples = X.shape[0]

        indexes = []
        hits = []
        misses = []

        for i in range(num_samples):
            distances = X_distances[i]
            nearest = np.argsort(distances)
            nearest_matrix = np.column_stack((nearest, [y[j] for j in nearest]))
            nearest_hits = np.array(list(filter(lambda row: row[1] == nearest_matrix[0, 1],
                                                nearest_matrix)))
            nearest_misses = np.array(list(filter(lambda row: row[1] != nearest_matrix[0, 1],
                                                  nearest_matrix)))
            k_nearest_hits = [row[0] for row in nearest_hits[1: (k + 1)]]
            k_nearest_misses = [row[0] for row in nearest_misses[:k]]

            indexes += [i for j in range(k)]
            hits += k_nearest_hits
            misses += k_nearest_misses

        # TODO: this sometimes fails when all class labels are different or when k != 1 is used
        hitmiss = np.array([np.column_stack((indexes, hits)),
                            np.column_stack((indexes, misses))])

        return hitmiss

    def fit(self, X, y, feature_names=None, k=1):
        """
            Computes the feature importance scores from the training data.

            Parameters
            ----------
            X : array-like, shape (n_samples, n_features) 
                Training instances to compute the feature importance scores from.
            y : array-like, shape (n_samples, )
                Training labels.
            feature_names : list of strings, optional
                In case you want to define feature names
            k : int, optional
                number of constant nearest hits/misses.

            Returns
            -------
            None
        """

        features = generate_features(X)
        X, y, feature_names = self._check_input(X, y, feature_names)
        new_features = generate_features(X)
        self.feature_names = dict(zip(features, feature_names))
        n_samples = X.shape[0]
        n_features = X.shape[1]
        weights = np.zeros(n_features)
        neighbors_index = self.find_neighbors(X, y, k)
        #range_vec = np.array(self.max_diff(X)) # TODO: probably should convert to float64 and add division by zero check
        range_vec = np.array(self.max_diff(X)).astype('float64')
        range_vec[range_vec == 0] = 1e-14
        one_over_range = 1 / range_vec
        one_over_m = 1 / n_samples

        hit_index, hits = np.hsplit(neighbors_index[0], 2)
        miss_index, misses = np.hsplit(neighbors_index[1], 2)

        hit_index = hit_index.flatten()
        hits = hits.flatten()
        miss_index = miss_index.flatten()
        misses = misses.flatten()

        for feature_index in new_features:
            attr_values = X.T[feature_index]

            hit_neighbors = np.array([attr_values[i] for i in hits])
            miss_neighbors = np.array([attr_values[i] for i in misses])

            hit_values = np.array([attr_values[i] for i in hit_index])
            miss_values = np.array([attr_values[i] for i in miss_index])

            attr_diff_hits = np.abs(hit_neighbors - hit_values) * one_over_range[feature_index]
            attr_diff_misses = np.abs(miss_neighbors - miss_values) * one_over_range[feature_index]

            mu_hits = np.sum(attr_diff_hits) / n_samples
            mu_misses = np.sum(attr_diff_misses) / n_samples

            weights[feature_index] = mu_misses - mu_hits

        self.feature_scores = weights * one_over_m * 1000
        self.selected_features = features[np.argsort(self.feature_scores)[::-1][:self.n_features_to_keep]]

    def transform(self, X):
        """
            Reduces the feature set down to the top `n_features_to_keep` features.

            Parameters
            ----------
            X : array-like, shape (n_samples, n_features) 
                Feature matrix to perform feature selection on.

            Returns
            -------
            Transformed 2D numpy array
        """

        if type(X) is np.ndarray:
            return X[:, self.selected_features.astype(int)]
        else:
            return X[self.selected_features]

    def fit_transform(self, X, y, feature_names=None, k=1):
        """
            Fits and transforms data.

            Computes the feature importance scores from the training data, then
            reduces the feature set down to the top 'n_features_to_keep' features.

            Parameters
            ----------
            X : array-like, shape (n_samples, n_features) 
                Training instances to compute the feature importance scores from.
            y : array-like, shape (n_samples, )
                Training labels.
            feature_names : list of strings, optional
                In case you want to define feature names
            k : int, optional
                number of constant nearest hits/misses.             

            Returns
            -------
            Transformed 2D numpy array
        """

        self.fit(X, y, feature_names, k)
        return self.transform(X)
