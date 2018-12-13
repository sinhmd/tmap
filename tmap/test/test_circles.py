from sklearn import datasets
from sklearn.cluster import DBSCAN
from tmap.tda import mapper, filter
from tmap.tda.cover import Cover
from tmap.tda.plot import show, Color


X, y = datasets.make_circles(n_samples=5000, noise=0.05, factor=0.3)

# Step1. initiate a Mapper
tm = mapper.Mapper(verbose=1)

# Step2. Projection
lens = [filter.PCA(components=[0, 1])]
projected_X = tm.filter(X, lens=lens)

# Step3. Covering, clustering & mapping
clusterer = DBSCAN(eps=0.1, min_samples=5)
cover = Cover(projected_data=projected_X, resolution=20, overlap=0.1)
graph = tm.map(data=X, cover=cover, clusterer=clusterer)

# Step4. Visualization
color = Color(target=y, dtype="categorical")
# show(data=X, graph=graph, color=color, fig_size=(10, 10), node_size=15, mode='spring', strength=0.04)

from tmap.tda.plot import vis_progressX
vis_progressX(graph,projected_X,color=Color(target=y,dtype='categorical',target_by='sample'))