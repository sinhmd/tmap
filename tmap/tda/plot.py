# -*- coding: utf-8 -*-
import colorsys

import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import plotly
import plotly.graph_objs as go
from scipy import stats
from sklearn import decomposition
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, maxabs_scale
from tmap.netx.SAFE import construct_node_data


class Color(object):
    """
    map colors to target values for TDA network visualization

    * If ``target_by`` set as *samples*, it means that it will pass original data instead of SAFE score for colorizing the node on the graph.
    * If ``node`` set as *node*, it means that it will pass SAFE score for colorizing the node on the graph. So the target must be a dictionary generated by SAFE_batch function. If you using single SAFE function called ``SAFE``, it will also create a dict which could be used.

    The basically code assign the highest values with red and the lowest values with blue. Before we assign the color, it will split the target into 4 parts with ``np.percentile`` and scale each part with different upper and lower boundary.

    It is normally have 4 distinct parts in color bar but it will easily missing some parts due to some skewness which misleading the values of percentile.

    :param list/np.ndarray/pd.Series/dict target: target values for samples or nodes
    :param str dtype: type of target values, "numerical" or "categorical"
    :param str target_by: target type of "sample" or "node"

    """

    def __init__(self, target, dtype="numerical", target_by="sample"):
        """
        :param list/np.ndarray/pd.Series target: target values for samples or nodes
        :param str dtype: type of target values, "numerical" or "categorical"
        :param str target_by: target type of "sample" or "node"
        (for node target values, accept a node associated dictionary of values)
        """
        if target is None:
            raise Exception("target must not be None.")

        # for node target values, accept a node associated dictionary of values
        if target_by == 'node':
            _target = np.zeros(len(target))
            for _node_idx, _node_val in target.items():
                _target[_node_idx] = _node_val
            target = _target

        if type(target) is not np.ndarray:
            target = np.array(target)
        if len(target.shape) == 1:
            target = target.reshape(-1, 1)
        if dtype not in ["numerical", "categorical"]:
            raise ValueError("data type must be 'numerical' or 'categorical'.")
        if target_by not in ["sample", "node"]:
            raise ValueError("target values must be by 'sample' or 'node'")
        # target values should be numbers, check and encode categorical labels

        if ((type(target[0][0]) != int)
                and (type(target[0][0]) != float)
                and (not isinstance(target[0][0], np.number))
        ):
            self.label_encoder = LabelEncoder()
            self.target = self.label_encoder.fit_transform(target.ravel())
        elif dtype == "categorical":
            self.label_encoder = LabelEncoder()
            self.target = self.label_encoder.fit_transform(target.astype(str).ravel())
        else:
            self.label_encoder = None
            self.target = target

        self.dtype = dtype
        self.labels = target.astype(str)
        self.target_by = target_by

    def _get_hex_color(self, i, cmap=None):
        """
        map a normalize i value to HSV colors
        :param i: input for the hue value, normalized to [0, 1.0]
        :return: a hex color code for i
        """
        # H values: from 0 (red) to 240 (blue), using the HSV color systems for color mapping
        # largest value of 1 mapped to red, and smallest of 0 mapped to blue
        c = colorsys.hsv_to_rgb((1 - i) * 240 / 360, 1.0, 0.75)
        return "#%02x%02x%02x" % (int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))

    def _rescale_target(self, target):
        """
        scale target values according to density/percentile
        to make colors distributing evenly among values
        :param target: numerical target values
        :return:
        """
        rescaled_target = np.zeros(target.shape)

        scaler_min_q1 = MinMaxScaler(feature_range=(0, 0.25))
        scaler_q1_median = MinMaxScaler(feature_range=(0.25, 0.5))
        scaler_median_q3 = MinMaxScaler(feature_range=(0.5, 0.75))
        scaler_q3_max = MinMaxScaler(feature_range=(0.75, 1))

        q1, median, q3 = np.percentile(target, 25), np.percentile(target, 50), np.percentile(target, 75)

        index_min_q1 = np.where(target <= q1)[0]
        index_q1_median = np.where(((target >= q1) & (target <= median)))[0]
        index_median_q3 = np.where(((target >= median) & (target <= q3)))[0]
        index_q3_max = np.where(target >= q3)[0]

        target_min_q1 = scaler_min_q1.fit_transform(target[index_min_q1]) if any(index_min_q1) else np.zeros(target[index_min_q1].shape)
        target_q1_median = scaler_q1_median.fit_transform(target[index_q1_median]) if any(index_q1_median) else np.zeros(target[index_q1_median].shape)
        target_median_q3 = scaler_median_q3.fit_transform(target[index_median_q3]) if any(index_median_q3) else np.zeros(target[index_median_q3].shape)
        target_q3_max = scaler_q3_max.fit_transform(target[index_q3_max]) if any(index_q3_max) else np.zeros(target[index_q3_max].shape)
        # in case the situation which will raise ValueError when sliced_index is all False.

        # using percentile to cut and assign colors will meet some special case which own weak distribution.
        # below `if` statement is trying to determine and solve these situations.
        if all(target_q3_max == 0.75):
            # all transformed q3 number equal to the biggest values 0.75.
            # if we didn't solve it, red color which representing biggest value will disappear.
            # solution: make it all into 1.
            target_q3_max = np.ones(target_q3_max.shape)
        if q1 == median == q3:
            # if the border of q1,median,q3 area are all same, it means the the distribution is extremely positive skewness.
            # Blue color which represents smallest value will disappear.
            # Solution: Make the range of transformed value output from the final quantile into 0-1.
            target_q3_max = np.array([_ if _ != 0.75 else 0 for _ in target_q3_max[:, 0]]).reshape(target_q3_max.shape)

        rescaled_target[index_median_q3] = target_median_q3
        rescaled_target[index_q1_median] = target_q1_median
        rescaled_target[index_min_q1] = target_min_q1
        rescaled_target[index_q3_max] = target_q3_max

        return rescaled_target

    def get_colors(self, nodes, cmap=None):
        """
        :param dict nodes: nodes from graph
        :param cmap: not implemented yet...
        :return: nodes colors with keys, and the color map of the target values
        :rtype: tuple (first is a dict node_ID:node_color, second is a tuple (node_ID_index,node_color))
        """
        # todo: accept a customzied color map [via the 'cmap' parameter]
        node_keys = nodes.keys()

        # map a color for each node
        node_color_target = np.zeros((len(nodes), 1))
        for i, node_id in enumerate(node_keys):
            if self.target_by == 'node':
                target_in_node = self.target[node_id]
            else:
                target_in_node = self.target[nodes[node_id]]

            # summarize target values from samples/nodes for each node
            if self.dtype == "categorical":
                # Return an array of the modal (most common) value in the passed array. (if more than one, the smallest is return)
                node_color_target[i] = stats.mode(target_in_node)[0][0]
            elif self.dtype == "numerical":
                node_color_target[i] = np.nanmean(target_in_node)
        if np.any(np.isnan(node_color_target)):
            print("Nan was found in the given target, Please check the input data.")
        _node_color_idx = self._rescale_target(node_color_target)
        node_colors = [self._get_hex_color(idx) for idx in _node_color_idx]

        return dict(zip(node_keys, node_colors)), (node_color_target, node_colors)

    def get_sample_colors(self, cmap=None):
        """
        :param dict nodes: nodes from graph
        :param cmap: not implemented yet...
        :return: nodes colors with keys, and the color map of the target values
        :rtype: tuple (first is a dict node_ID:node_color, second is a tuple (node_ID_index,node_color))
        """
        if self.target_by != "sample":
            raise IOError

        if self.dtype == "numerical":
            _sample_color_idx = self._rescale_target(self.target)
        else:
            labels = self.label_encoder.inverse_transform(self.target)
            _sample_color_idx = np.arange(0.0, 1.1, 1.0 / (len(set(labels))-1)) # add 1 into idx, so it is 1.1 which is little bigger than 1.
            target2idx = dict(zip(sorted(set(labels)),_sample_color_idx))

        if type(cmap) == dict and self.dtype == 'categorical':
            sample_colors = [cmap.get(_, 'blue') for _ in labels]
            # implement for custom cmap for categorical values.
        elif self.dtype == "numerical":
            sample_colors = [self._get_hex_color(idx) for idx in _sample_color_idx]
        else:
            sample_colors = [self._get_hex_color(target2idx[label]) for label in labels]
        return sample_colors,target2idx


def show(data, graph, color=None, fig_size=(10, 10), node_size=10, edge_width=2, mode=None, strength=None):
    """
    Network visualization of TDA mapper

    Using matplotlib as basic engine, it is easily add title or others elements.

    :param np.ndarray/pd.DataFrame data:
    :param dict graph:
    :param Color/str color: Passing ``tmap.tda.plot.Color`` or just simply color string.
    :param tuple fig_size: height and width
    :param int node_size: With given node_size, it will scale all nodes with same size ``node_size/max(node_sizes) * node_size **2``. The size of nodes also depends on the biggest node which contains maxium number of samples.
    :param int edge_width: Line width of edges.
    :param str/None mode: Currently, Spring layout is the only one style supported.
    :param float strength: Optimal distance between nodes.  If None the distance is set to ``1/sqrt(n)`` where n is the number of nodes.  Increase this value to move nodes farther apart.
    :return: plt.figure
    """
    # todo: add file path for graph saving
    node_keys = graph["node_keys"]
    node_positions = graph["node_positions"]
    node_sizes = graph["node_sizes"]

    # scale node sizes
    max_node_size = np.max(node_sizes)
    sizes = (node_sizes / max_node_size) * (node_size ** 2)

    # map node colors
    if color is None or type(color) == str:
        if color is None:
            color = 'red'
        color_map = {node_id: color for node_id in node_keys}
        target2colors = (np.zeros((len(node_keys), 1)), [color] * len(node_keys))
    else:
        color_map, target2colors = color.get_colors(graph["nodes"])
    colorlist = [color_map[it] for it in node_keys]

    node_target_values, node_colors = target2colors
    legend_lookup = dict(zip(node_target_values.reshape(-1, ), node_colors))

    # if there are indicated color with ``Color``, it need to add some legend for given color.
    if isinstance(color, Color):

        if color.dtype == "categorical":
            fig = plt.figure(figsize=fig_size)
            ax = fig.add_subplot(1, 1, 1)
            if color.label_encoder:
                encoded_cat = color.label_encoder.transform(color.labels.ravel())
                # if color.label_encoder exist, color.labels must be some kinds of string list which is need to encoded.
            else:
                encoded_cat = color.labels.ravel()
                # if not, it should be used directly as the node_target_values.
            label_color = [legend_lookup.get(e_cat, None) for e_cat in encoded_cat]
            get_label_color_dict = dict(zip(encoded_cat, label_color))

            # add categorical legend
            for label in sorted(set(encoded_cat)):
                if label_color is not None:
                    ax.plot([], [], 'o', color=get_label_color_dict[label], label=label, markersize=10)

            legend = ax.legend(numpoints=1, loc="upper right")
            legend.get_frame().set_facecolor('#bebebe')

        # add numerical colorbar
        elif color.dtype == "numerical":
            fig = plt.figure(figsize=(fig_size[0] * 10 / 9, fig_size[1]))
            ax = fig.add_subplot(1, 1, 1)
            legend_values = sorted([val for val in legend_lookup])
            legned_colors = [legend_lookup.get(val, 'blue') for val in legend_values]

            # add color bar
            # TODO: Implement more details of color bar and make it more robust.
            cmap = mcolors.LinearSegmentedColormap.from_list('my_cmap', legned_colors)
            norm = mcolors.Normalize(min(legend_values), max(legend_values))
            sm = cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])

            cb = fig.colorbar(sm,
                              shrink=0.5,
                              pad=0.1)
            cb.ax.yaxis.set_ticks_position('right')
            if min(legend_values) != 0:
                # if minimum values of legend is not 0, it need to add a text to point out the minimum values.
                if min(legend_values) * 100 >= 0.1:
                    # Determine whether the minimum value is too small to visualize pretty.
                    # .2f indicates accurate to the second decimal place.
                    # .2e indicated accurate to the second decimal after scientific notation.
                    cb.ax.text(0.5, -0.02, '{:.2f}'.format(min(legend_values)), ha='center', va='top', weight='bold')
                else:
                    cb.ax.text(0.5, -0.02, '{:.2e}'.format(min(legend_values)), ha='center', va='top', weight='bold')

            if max(legend_values) * 100 >= 0.1:
                # same as the minimum values
                cb.ax.text(0.5, 1.02, '{:.2f}'.format(max(legend_values)), ha='center', va='bottom', weight='bold')
            else:
                cb.ax.text(0.5, 1.02, '{:.2e}'.format(max(legend_values)), ha='center', va='bottom', weight='bold')

    if mode == 'spring':
        pos = {}
        # the projection space is one dimensional
        if node_positions.shape[1] == 1:
            m = decomposition.PCA(n_components=2)
            s = MinMaxScaler()
            d = m.fit_transform(data)
            d = s.fit_transform(d)
            for k in node_keys:
                data_in_node = d[graph['nodes'][k]]
                pos.update({int(k): np.average(data_in_node, axis=0)})
        elif node_positions.shape[1] >= 2:
            for i, k in enumerate(node_keys):
                pos.update({int(k): node_positions[i, :2]})

        G = nx.Graph(pos=pos)
        G.add_nodes_from(node_keys)
        G.add_edges_from(graph["edges"])
        pos = nx.spring_layout(G, pos=pos, k=strength)
        # add legend
        nx.draw_networkx(G, pos=pos,
                         node_size=sizes,
                         node_color=colorlist,
                         width=edge_width,
                         edge_color=[color_map[edge[0]] for edge in graph["edges"]],
                         with_labels=False, ax=ax)

    else:
        fig = plt.figure(figsize=fig_size)
        ax = fig.add_subplot(111)
        node_idx = dict(zip(node_keys, range(len(node_keys))))
        for edge in graph["edges"]:
            ax.plot([node_positions[node_idx[edge[0]], 0], node_positions[node_idx[edge[1]], 0]],
                    [node_positions[node_idx[edge[0]], 1], node_positions[node_idx[edge[1]], 1]],
                    c=color_map[edge[0]], zorder=1)
        ax.scatter(node_positions[:, 0], node_positions[:, 1],
                   c=colorlist, s=sizes, zorder=2)

    plt.axis("off")
    plt.show()


def get_arrows(graph, projected_X, safe_score, max_length=1, pvalue=0.05):
    min_p_value = 1.0 / (5000 + 1.0)
    threshold = np.log10(pvalue) / np.log10(min_p_value)

    node_pos = construct_node_data(graph, projected_X)

    safe_score_df = pd.DataFrame.from_dict(safe_score, orient='columns')
    safe_score_df = safe_score_df.where(safe_score_df >= threshold, other=0)
    norm_df = safe_score_df.apply(lambda x: maxabs_scale(x), axis=1, result_type='broadcast')

    x_cor = norm_df.apply(lambda x: x * node_pos.values[:, 0], axis=0)
    y_cor = norm_df.apply(lambda x: x * node_pos.values[:, 1], axis=0)

    x_cor = x_cor.mean(0)
    y_cor = y_cor.mean(0)
    arrow_df = pd.DataFrame([x_cor, y_cor], index=['x coordinate', 'y coordinate'], columns=safe_score_df.columns)
    all_fea_scale = maxabs_scale(safe_score_df.sum(0))
    # scale each arrow by the sum of safe score， maximun is 1 others are percentage not larger than 100%.
    scaled_ratio = max_length * all_fea_scale / arrow_df.apply(lambda x: np.sqrt(np.sum(x ** 2)), axis=0)
    # using max length to multipy by scale ratio and denote the original length.
    scaled_arrow_df = arrow_df * np.repeat(scaled_ratio.values.reshape(1, -1), axis=0, repeats=2).reshape(2, -1)

    return scaled_arrow_df


def vis_progressX(graph, projected_X, simple=False, mode='file', color=None, _color_SAFE=None, **kwargs):
    """
    For dynamic visualizing tmap construction process, it performs a interactive graph based on `plotly` with a slider to present the process from ordination to graph step by step. Currently, it doesn't provide any API for overriding the number of step from ordination to graph. It may be implemented at the future.

    If you want to draw a simple graph with edges and nodes instead of the process,  try the params ``simple``.

    This visualized function is mainly based on plotly which is a interactive Python graphing library. The params mode is trying to provide multiple type of return for different purpose. There are three different modes you can choose including "file" which return a html created by plotly, "obj" which return a reusable python dict object and "web" which normally used at notebook and make inline visualization possible.

    The color part of this function has a little bit complex because of the multiple sub-figures. Currently, it use the ``tmap.tda.plot.Color`` class to auto generate color with given array. More detailed about how to auto generate color could be reviewed at the annotation of ``tmap.tda.plot.Color``.
    In this function,  there are two kinds of color need to implement.
        First, all color and its showing text values of samples points should be followed by given color params. The color could be **any array** which represents some measurement of Nodes or Samples. **It doesn't have to be SAFE score. **
        Second, The ``_color_SAFE`` param should be a ``Color`` with a nodes-length array, which is normally a SAFE score.


    :param graph:
    :param np.array projected_X:
    :param str mode: [file|obj|web]
    :param bool simple:
    :param color:
    :param _color_SAFE:

    :param kwargs:
    :return:
    """
    node_pos = graph["node_positions"]
    ori_MDS = projected_X
    nodes = graph["nodes"]
    sizes = graph["node_sizes"][:, 0]
    sample_names = np.array(graph.get("sample_names", []))

    if color:
        color_map, target2colors = color.get_colors(graph["nodes"])
    else:
        color = Color([0] * projected_X.shape[0])

    if color.target_by == "node":
        samples_colors = "red"
    else:
        samples_colors,cat2colors = color.get_sample_colors()

    # For calculating the dynamic process. It need to be aligned first.
    # reconstructing the ori_MDS into the samples_pos
    # reconstructing the node_pos into the center_pos
    point_tmp = []
    center_tmp = []
    text_tmp = []
    samples_colors_dynamic = []
    for n in nodes:
        point_tmp.append(ori_MDS[nodes[n], :])
        center_tmp.append(np.concatenate([node_pos[[n], :]] * len(nodes[n]), axis=0))
        text_tmp.append(sample_names[nodes[n]])
        if color:
            samples_colors_dynamic += list(np.repeat(color_map[n], len(nodes[n])))
        else:
            samples_colors_dynamic.append("blue")
    samples_pos = np.concatenate(point_tmp, axis=0)
    center_pos = np.concatenate(center_tmp, axis=0)
    broadcast_samples_text = np.concatenate(text_tmp, axis=0)
    # For visualizing the movement of samples, it need to multiply one sample into multiple samples which is need to reconstruct pos,text.

    node_pos = graph["node_positions"]
    # prepare edge data
    xs = []
    ys = []
    for edge in graph["edges"]:
        xs += [node_pos[edge[0], 0],
               node_pos[edge[1], 0],
               None]
        ys += [node_pos[edge[0], 1],
               node_pos[edge[1], 1],
               None]

    # prepare node & samples text
    node_vis_vals = [np.mean(color.target[nodes[n]]) if color.target_by == "sample" else str(color.target[n]) for n in graph["nodes"]]
    # values output from color.target. It need to apply mean function for a samples-length color.target.
    node_text = [str(n) +
                 # node id
                 "<Br>vals:%s<Br>" % str(v) +
                 # node values output from color.target.
                 '<Br>'.join(np.array(graph.get("sample_names")).astype(str)[graph["nodes"][n]]) for n, v in
                 # samples name concated with line break.
                 zip(graph["nodes"],
                     node_vis_vals)]
    ### samples text
    samples_text = ['sample ID:%s' % _ for _ in graph.get("sample_names", [])]

    # if there are _color_SAFE, it will present two kinds of color.
    # one is base on original data, one is transformed-SAFE data.
    if _color_SAFE is not None:
        safe_color, safe_t2c = _color_SAFE.get_colors(graph["nodes"])
        node_colors = [safe_color[_] for _ in range(len(nodes))]
    else:
        node_colors = [color_map[_] for _ in range(len(nodes))]

    node_line = go.Scatter(
        # ordination line
        visible=False,
        x=xs,
        y=ys,
        marker=dict(color="#8E9DA2",
                    opacity=0.7),
        line=dict(width=1),
        showlegend=False,
        mode="lines")
    node_position = go.Scatter(
        # node position
        visible=False,
        x=node_pos[:, 0],
        y=node_pos[:, 1],
        text=node_text,
        hoverinfo="text",
        marker=dict(color=node_colors,
                    size=[5 + sizes[_] for _ in range(len(nodes))],
                    opacity=1),
        showlegend=False,
        mode="markers")
    samples_position = go.Scatter(
        visible=True,
        x=ori_MDS[:, 0],
        y=ori_MDS[:, 1],
        marker=dict(color=samples_colors),
        text=samples_text,
        hoverinfo="text",
        showlegend=False,
        mode="markers")
    ### After all prepared work have been finished.
    # Append all traces instance into fig

    if simple:
        fig = plotly.tools.make_subplots(1, 1)
        node_line['visible'] = True
        node_position['visible'] = True
        fig.append_trace(node_line, 1, 1)
        fig.append_trace(node_position, 1, 1)

    else:
        fig = plotly.tools.make_subplots(rows=2, cols=2, specs=[[{'rowspan': 2}, {}], [None, {}]],
                                         # subplot_titles=('Mapping process', 'Original projection', 'tmap graph')
                                         )
        # original place or ordination place
        fig.append_trace(samples_position, 1, 1)

        # dynamic process to generate 5 binning positions
        n_step = 5
        for s in range(1, n_step + 1):
            # s = 1: move 1/steps
            # s = steps: move to node position.
            fig.append_trace(go.Scatter(
                visible=False,
                x=samples_pos[:, 0] + ((center_pos - samples_pos) / n_step * s)[:, 0],
                y=samples_pos[:, 1] + ((center_pos - samples_pos) / n_step * s)[:, 1],
                marker=dict(color=samples_colors_dynamic),
                hoverinfo="text",
                text=broadcast_samples_text,
                showlegend=False,
                mode="markers"), 1, 1)

        # Order is important, do not change the order !!!
        # This is the last 5 should be visible at any time
        fig.append_trace(node_line, 1, 1)
        fig.append_trace(node_position, 1, 1)
        node_line['visible'] = True
        node_position['visible'] = True
        samples_position['visible'] = True
        fig.append_trace(node_line, 2, 2)
        fig.append_trace(node_position, 2, 2)
        fig.append_trace(samples_position, 1, 2)
        ############################################################
        steps = []
        for i in range(n_step + 1):
            step = dict(
                method='restyle',
                args=['visible', [False] * (n_step + 3) + [True, True, True]],
            )
            if i >= n_step:
                step["args"][1][-5:] = [True] * 5  # The last 5 should be some traces must present at any time.
            else:
                step['args'][1][i] = True  # Toggle i'th trace to "visible"
            steps.append(step)

        sliders = [dict(
            active=0,
            currentvalue={"prefix": "status: "},
            pad={"t": 20},
            steps=steps
        )]
        ############################################################
        layout = dict(sliders=sliders,
                      width=2000,
                      height=1000,
                      xaxis1={  # "range": [0, 1],
                          "domain": [0, 0.5]},
                      yaxis1={  # "range": [0, 1],
                          "domain": [0, 1]},
                      xaxis2={  # "range": [0, 1],
                          "domain": [0.6, 0.9]},
                      yaxis2={  # "range": [0, 1],
                          "domain": [0.5, 1]},
                      xaxis3={  # "range": [0, 1],
                          "domain": [0.6, 0.9]},
                      yaxis3={  # "range": [0, 1],
                          "domain": [0, 0.5]},
                      hovermode="closest"
                      )
        fig.layout.update(layout)

    if mode == 'file':
        plotly.offline.plot(fig, **kwargs)

    elif mode == 'web':
        plotly.offline.iplot(fig, **kwargs)
    elif mode == 'obj':
        return fig
    else:
        print("mode params must be one of 'file', 'web', 'obj'. \n 'file': output html file \n 'web': show in web browser. \n 'obj': return a dict object.")


def draw_enriched_plot(graph, safe_score, fea, metainfo, _filter_size=0, **kwargs):
    """
    Draw simple node network which only show component which is larger than _filter_size and colorized with
    its safe_score.

    :param graph:
    :param safe_score:
    :param fea:
    :param metainfo:
    :param _filter_size:
    :param kwargs:
    :return:
    """
    enriched_nodes, comps_nodes = metainfo[fea]

    node_pos = graph["node_positions"]
    sizes = graph["node_sizes"][:, 0]
    fig = plotly.tools.make_subplots(1, 1)
    xs = []
    ys = []

    for edge in graph["edges"]:
        xs += [node_pos[edge[0], 0],
               node_pos[edge[1], 0],
               None]
        ys += [node_pos[edge[0], 1],
               node_pos[edge[1], 1],
               None]

    node_line = go.Scatter(
        # ordination line
        visible=True,
        x=xs,
        y=ys,
        hoverinfo='none',
        marker=dict(color="#8E9DA2", ),
        line=dict(width=1),
        showlegend=False,
        mode="lines")

    fig.append_trace(node_line, 1, 1)

    for idx, nodes in enumerate(comps_nodes):
        if _filter_size:
            if len(nodes) <= _filter_size:
                continue
        tmp1 = {k: v if k in nodes else np.nan for k, v in safe_score[fea].items()}
        node_position = go.Scatter(
            # node position
            visible=True,
            x=node_pos[[k for k, v in safe_score[fea].items() if not np.isnan(tmp1[k])], 0],
            y=node_pos[[k for k, v in safe_score[fea].items() if not np.isnan(tmp1[k])], 1],
            hoverinfo="text",
            text=['node:%s,SAFE:%s' % (k, safe_score[fea][k]) for k, v in safe_score[fea].items() if not np.isnan(tmp1[k])],
            marker=dict(  # color=node_colors,
                size=[7 + sizes[_] for _ in [k for k, v in safe_score[fea].items() if not np.isnan(tmp1[k])]],
                opacity=0.8),
            showlegend=True,
            name='comps_%s' % idx,
            mode="markers")
        fig.append_trace(node_position, 1, 1)

    fig.layout.font.size = 15
    fig.layout.title = fea
    fig.layout.height = 1500
    fig.layout.width = 1500
    fig.layout.hovermode = 'closest'
    plotly.offline.plot(fig, **kwargs)


def draw_coenrichment_ranksum(metainfo, fea, others, node_data, node_metadata, **kwargs):
    for o_f in others:
        fig = go.Figure()
        s1, s2, s3, s4 = metainfo[o_f]

        if o_f in node_data.columns:
            _data = node_data
        elif o_f in node_metadata.columns:
            _data = node_metadata
        else:
            print('error feature %s' % o_f)
            return
        y1 = _data.loc[s1, o_f]
        y2 = _data.loc[set.union(s2, s3, s4), o_f]

        if fea in node_data.columns:
            _data = node_data
        elif fea in node_metadata.columns:
            _data = node_metadata
        _y1 = _data.loc[s1, fea]
        _y2 = _data.loc[set.union(s2, s3, s4), fea]
        # ranksum_p1 = scs.ranksums(y1, y2)[1]
        # ranksum_p2 = scs.ranksums(_y1, _y2)[1]

        datas = []
        datas.append(go.Box(y=y1, x='%s enriched' % o_f))
        datas.append(go.Box(y=y2, x='%s non-enriched' % o_f))

        datas.append(go.Box(y=_y1, x='%s enriched' % fea))
        datas.append(go.Box(y=_y2, x='%s non-enriched' % fea))
        fig.data += datas
        plotly.offline.plot(fig, **kwargs)
