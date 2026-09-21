"""Stage 3 `cluster`: KMeans over visual embeddings, k by silhouette.

k is searched in 2..min(15, n//3); the k with the best silhouette score
wins. 2 reps per cluster (nearest to centroid). n < 4 → single cluster.
"""

import logging

import numpy as np

log = logging.getLogger("tempo.cluster")


def choose_k(embs: np.ndarray) -> int:
    """Best k by silhouette; 0 means 'single cluster' (n < 4)."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    n = len(embs)
    if n < 4:
        return 0
    best_k, best_score = 2, -1.0
    for k in range(2, min(15, n // 3) + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(embs)
        score = silhouette_score(embs, labels, sample_size=min(1000, n))
        if score > best_score:
            best_k, best_score = k, score
    return best_k


def cluster_shots(visual: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Returns (labels, rep_indices) with 2 reps per cluster."""
    from sklearn.cluster import KMeans

    n = len(visual)
    k = choose_k(visual)
    if k == 0:
        return np.zeros(n, dtype=int), list(range(min(2, n)))
    labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(visual)
    reps: list[int] = []
    for c in range(k):
        members = np.where(labels == c)[0]
        centroid = visual[members].mean(axis=0)
        order = members[np.argsort(((visual[members] - centroid) ** 2).sum(axis=1))]
        top_n = 2 if len(members) >= 3 else 1  # research artifact rule
        reps.extend(order[:top_n].tolist())
    log.info("clustered %d shots into k=%d (%d reps)", n, k, len(reps))
    return labels, reps
