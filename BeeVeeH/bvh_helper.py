import BeeVeeH.bvh as BVHLIB
import math
import copy
import numpy as np
from collections import Iterable


class BVHChannel(object):
    ChannelTransformMatrixMap = {
            'Xposition': lambda x: np.array([[1, 0, 0, x],
                                             [0, 1, 0, 0],
                                             [0, 0, 1, 0],
                                             [0, 0, 0, 1]]),
            'Yposition': lambda x: np.array([[1, 0, 0, 0],
                                             [0, 1, 0, x],
                                             [0, 0, 1, 0],
                                             [0, 0, 0, 1]]),
            'Zposition': lambda x: np.array([[1, 0, 0, 0],
                                             [0, 1, 0, 0],
                                             [0, 0, 1, x],
                                             [0, 0, 0, 1]]),
            'Xrotation': lambda x: np.array([[1, 0, 0, 0],
                                             [0, math.cos(math.radians(x)), -math.sin(math.radians(x)), 0],
                                             [0, math.sin(math.radians(x)), math.cos(math.radians(x)), 0],
                                             [0, 0, 0, 1]]),
            'Yrotation': lambda x: np.array([[math.cos(math.radians(x)), 0, math.sin(math.radians(x)), 0],
                                             [0, 1, 0, 0],
                                             [-math.sin(math.radians(x)), 0, math.cos(math.radians(x)), 0],
                                             [0, 0, 0, 1]]),
            'Zrotation': lambda x: np.array([[math.cos(math.radians(x)), -math.sin(math.radians(x)), 0, 0],
                                             [math.sin(math.radians(x)), math.cos(math.radians(x)), 0, 0],
                                             [0, 0, 1, 0],
                                             [0, 0, 0, 1]])
        }
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.value = 0.0

    def set_value(self, value):
        self.value = value

    def matrix(self):
        return BVHChannel.ChannelTransformMatrixMap[self.name](self.value)

    def str(self):
        return 'Channel({name}) = {value}'.format(name=self.name, value=self.value)


class BVHNode(object):
    def __init__(self, key, name, offsets, channel_names, children, weight=1):
        super().__init__()
        self.key = key
        self.name = name
        self.children = children # []
        self.channels = [BVHChannel(cn) for cn in channel_names] # []
        self.offsets = offsets # x, y, z
        # weight for calculate frame-frame distance
        self.weight = weight

        self.coordinates = []
        self.localTrans = []

    def search_node(self, name):
        if self.name == name:
            return self
        for child in self.children:
            result = child.search_node(name)
            if result:
                return result
        return None

    def filter(self, key):
        for child in self.children:
            if child.key == key:
                yield child

    def __load_frame(self, frame_data_array):
        ''' 
            this function modify frame_data_array, so 
            make sure you only call load_frame instead of this
        '''
        for channel in self.channels:
            channel.set_value(frame_data_array.pop(0))
        for child in self.children:
            child.__load_frame(frame_data_array)

    def load_frame(self, frame_data_array):
        frame_data_array = copy.copy(frame_data_array)
        self.__load_frame(frame_data_array)

    def apply_transformation(self, parent_tran_matrix=np.identity(4)):
        # calculate local trans
        self.localTrans = np.identity(4)
        for channel in self.channels:
            self.localTrans = np.dot(self.localTrans, channel.matrix())
        # calculate total trans
        tran_matrix = np.dot(parent_tran_matrix, self.localTrans)
        # calculate coordinates
        cor = np.array([self.offsets]).T
        self.coordinates = np.dot(tran_matrix, np.append(cor, [[1]], axis=0))[:3]
        # iterate the children
        for child in self.children:
            child.apply_transformation(tran_matrix)

    def str(self, show_coordinates=False):
        s = 'Node({name}), offset({offset})\n'\
                .format(name=self.name,
                        offset=', '.join([str(o) for o in self.offsets]))
        if show_coordinates:
            try:
                s = s + '\tWorld coordinates: (%.2f, %.2f, %.2f)\n' % (self.coordinates[0],
                                                                       self.coordinates[1],
                                                                       self.coordinates[2])
            except Exception as e:
                print('World coordinates is not available, call apply_transformation() first')
        s = s + '\tChannels:\n'
        for channel in self.channels:
            s = s + '\t\t' + channel.str() + '\n'
        for child in self.children:
            lines = child.str(show_coordinates=show_coordinates).split('\n')
            for line in lines:
                s = s + '\t' + line + '\n'
        return s

    def distance(node_a, node_b):
        assert(node_a.name == node_b.name and node_a.weight == node_b.weight)
        distance = np.linalg.norm(node_a.coordinates - node_b.coordinates) * node_a.weight
        for child_a, child_b in zip(node_a.children, node_b.children):
            distance += BVHNode.distance(child_a, child_b)
        return distance

    def frame_distance(self, frame_a, frame_b):
        root_a = copy.deepcopy(self)
        root_a.load_frame(frame_a)
        root_a.apply_transformation()
        root_b = copy.deepcopy(self)
        root_b.load_frame(frame_b)
        root_b.apply_transformation()
        return BVHNode.distance(root_a, root_b)


def __parse_bvh_node(bvhlib, bvhlib_node):
    '''This function parses object from bvh-python (https://github.com/20tab/bvh-python)'''
    key = bvhlib_node.value[0]
    name = bvhlib_node.name
    offsets = [float(f) for f in bvhlib_node.children[0].value[1:]]
    channel_names = []
    for channels in bvhlib_node.filter('CHANNELS'):
        channel_names = [c for c in channels.value[2:]]
    children = []
    for c in __filter_bvh_keys(bvhlib_node, ['JOINT', 'End']):
        children.append(__parse_bvh_node(bvhlib, c))
    node = BVHNode(key, name, offsets, channel_names, children)
    return node


def __filter_bvh_keys(bvhNode, keys):
    for child in bvhNode.children:
        if isinstance(keys, Iterable):
            if child.value[0] in keys:
                yield child
        elif child.value[0] == keys:
            yield child


def load(file_path):
    # open the *.bvh file
    with open(file_path, 'r') as f:
        bvhlib = BVHLIB.Bvh(f.read())

    joints = []

    def iterate_joints(joint):
        joints.append(joint)
        for child in __filter_bvh_keys(joint, ['JOINT', 'End']):
            iterate_joints(child)

    iterate_joints(next(bvhlib.root.filter('ROOT')))

    root = __parse_bvh_node(bvhlib, joints[0])
    return root, [[float(f) for f in frame] for frame in bvhlib.frames], bvhlib.frame_time

