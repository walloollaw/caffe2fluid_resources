### generated by caffe2fluid, your net is in class "AlexNet" ###

import sys
import os
import math
import numpy as np


def import_fluid():
    import paddle.fluid as fluid
    return fluid


def layer(op):
    '''Decorator for composable network layers.'''

    def layer_decorated(self, *args, **kwargs):
        # Automatically set a name if not provided.
        name = kwargs.setdefault('name', self.get_unique_name(op.__name__))
        # Figure out the layer inputs.
        if len(self.terminals) == 0:
            raise RuntimeError('No input variables found for layer %s.' % name)
        elif len(self.terminals) == 1:
            layer_input = self.terminals[0]
        else:
            layer_input = list(self.terminals)

        # Perform the operation and get the output.
        layer_output = op(self, layer_input, *args, **kwargs)
        # Add to layer LUT.
        self.layers[name] = layer_output
        # This output is now the input for the next layer.
        self.feed(layer_output)
        # Return self for chained calls.
        return self

    return layer_decorated


class Network(object):
    def __init__(self, inputs, trainable=True):
        # The input nodes for this network
        self.inputs = inputs
        # The current list of terminal nodes
        self.terminals = []
        # Mapping from layer names to layers
        self.layers = dict(inputs)
        # If true, the resulting variables are set as trainable
        self.trainable = trainable
        # Switch variable for dropout
        self.paddle_env = None
        self.setup()

    def setup(self):
        '''Construct the network. '''
        raise NotImplementedError('Must be implemented by the subclass.')

    def load(self, data_path, exe=None, place=None, ignore_missing=False):
        '''Load network weights.
        data_path: The path to the numpy-serialized network weights
        ignore_missing: If true, serialized weights for missing layers are ignored.
        '''
        fluid = import_fluid()
        #load fluid mode directly
        if os.path.isdir(data_path):
            assert (exe is not None), \
                'must provide a executor to load fluid model'
            fluid.io.load_persistables(executor=exe, dirname=data_path)
            return True

        #load model from a npy file
        if exe is None or place is None:
            if self.paddle_env is None:
                place = fluid.CPUPlace()
                exe = fluid.Executor(place)
                self.paddle_env = {'place': place, 'exe': exe}
                exe = exe.run(fluid.default_startup_program())
            else:
                place = self.paddle_env['place']
                exe = self.paddle_env['exe']

        data_dict = np.load(data_path).item()
        for op_name in data_dict:
            layer = self.layers[op_name]
            for param_name, data in data_dict[op_name].iteritems():
                try:
                    name = '%s_%s' % (op_name, param_name)
                    v = fluid.global_scope().find_var(name)
                    w = v.get_tensor()
                    w.set(data, place)
                except ValueError:
                    if not ignore_missing:
                        raise
        return True

    def feed(self, *args):
        '''Set the input(s) for the next operation by replacing the terminal nodes.
        The arguments can be either layer names or the actual layers.
        '''
        assert len(args) != 0
        self.terminals = []
        for fed_layer in args:
            if isinstance(fed_layer, basestring):
                try:
                    fed_layer = self.layers[fed_layer]
                except KeyError:
                    raise KeyError('Unknown layer name fed: %s' % fed_layer)
            self.terminals.append(fed_layer)
        return self

    def get_output(self):
        '''Returns the current network output.'''
        return self.terminals[-1]

    def get_unique_name(self, prefix):
        '''Returns an index-suffixed unique name for the given prefix.
        This is used for auto-generating layer names based on the type-prefix.
        '''
        ident = sum(t.startswith(prefix) for t, _ in self.layers.items()) + 1
        return '%s_%d' % (prefix, ident)

    @layer
    def conv(self,
             input,
             k_h,
             k_w,
             c_o,
             s_h,
             s_w,
             name,
             relu=True,
             relu_negative_slope=0.0,
             padding=None,
             group=1,
             biased=True):
        if padding is None:
            padding = [0, 0]

        # Get the number of channels in the input
        c_i, h_i, w_i = input.shape[1:]

        # Verify that the grouping parameter is valid
        assert c_i % group == 0
        assert c_o % group == 0

        fluid = import_fluid()
        prefix = name + '_'
        leaky_relu = False
        act = 'relu'
        if relu is False:
            act = None
        elif relu_negative_slope != 0.0:
            leaky_relu = True
            act = None

        output = fluid.layers.conv2d(
            input=input,
            filter_size=[k_h, k_w],
            num_filters=c_o,
            stride=[s_h, s_w],
            padding=padding,
            groups=group,
            param_attr=fluid.ParamAttr(name=prefix + "weights"),
            bias_attr=fluid.ParamAttr(name=prefix + "biases"),
            act=act)

        if leaky_relu:
            output = fluid.layers.leaky_relu(output, alpha=relu_negative_slope)

        return output

    @layer
    def relu(self, input, name):
        fluid = import_fluid()
        output = fluid.layers.relu(x=input)
        return output

    def pool(self, pool_type, input, k_h, k_w, s_h, s_w, ceil_mode, padding,
             name):
        # Get the number of channels in the input
        in_hw = input.shape[2:]
        k_hw = [k_h, k_w]
        s_hw = [s_h, s_w]

        fluid = import_fluid()
        output = fluid.layers.pool2d(
            input=input,
            pool_size=k_hw,
            pool_stride=s_hw,
            pool_padding=padding,
            ceil_mode=ceil_mode,
            pool_type=pool_type)
        return output

    @layer
    def max_pool(self,
                 input,
                 k_h,
                 k_w,
                 s_h,
                 s_w,
                 ceil_mode,
                 padding=[0, 0],
                 name=None):
        return self.pool('max', input, k_h, k_w, s_h, s_w, ceil_mode, padding,
                         name)

    @layer
    def avg_pool(self,
                 input,
                 k_h,
                 k_w,
                 s_h,
                 s_w,
                 ceil_mode,
                 padding=[0, 0],
                 name=None):
        return self.pool('avg', input, k_h, k_w, s_h, s_w, ceil_mode, padding,
                         name)

    @layer
    def sigmoid(self, input, name):
        fluid = import_fluid()
        return fluid.layers.sigmoid(input)

    @layer
    def lrn(self, input, radius, alpha, beta, name, bias=1.0):
        fluid = import_fluid()
        output = fluid.layers.lrn(input=input, \
                n=radius, k=bias, alpha=alpha, beta=beta, name=name)
        return output

    @layer
    def concat(self, inputs, axis, name):
        fluid = import_fluid()
        output = fluid.layers.concat(input=inputs, axis=axis)
        return output

    @layer
    def add(self, inputs, name):
        fluid = import_fluid()
        output = inputs[0]
        for i in inputs[1:]:
            output = fluid.layers.elementwise_add(x=output, y=i)
        return output

    @layer
    def fc(self, input, num_out, name, relu=True, act=None):
        fluid = import_fluid()

        if act is None:
            act = 'relu' if relu is True else None

        prefix = name + '_'
        output = fluid.layers.fc(
            name=name,
            input=input,
            size=num_out,
            act=act,
            param_attr=fluid.ParamAttr(name=prefix + 'weights'),
            bias_attr=fluid.ParamAttr(name=prefix + 'biases'))
        return output

    @layer
    def softmax(self, input, name):
        fluid = import_fluid()
        shape = input.shape
        if len(shape) > 2: 
            for sz in shape[2:]:
                assert sz == 1, "invalid input shape[%s] for softmax" % (str(shape))
            input = fluid.layers.reshape(input, shape[0:2])

        output = fluid.layers.softmax(input)
        return output

    @layer
    def batch_normalization(self,
                            input,
                            name,
                            scale_offset=True,
                            eps=1e-5,
                            relu=False):
        # NOTE: Currently, only inference is supported
        fluid = import_fluid()
        prefix = name + '_'
        param_attr = None if scale_offset is False else fluid.ParamAttr(
            name=prefix + 'scale')
        bias_attr = None if scale_offset is False else fluid.ParamAttr(
            name=prefix + 'offset')
        mean_name = prefix + 'mean'
        variance_name = prefix + 'variance'
        output = fluid.layers.batch_norm(
            name=name,
            input=input,
            is_test=True,
            param_attr=param_attr,
            bias_attr=bias_attr,
            moving_mean_name=mean_name,
            moving_variance_name=variance_name,
            epsilon=eps,
            act='relu' if relu is True else None)

        return output

    @layer
    def dropout(self, input, drop_prob, name, is_test=True):
        fluid = import_fluid()
        if is_test:
            output = input
        else:
            output = fluid.layers.dropout(
                input, dropout_prob=drop_prob, is_test=is_test)
        return output

    @layer
    def scale(self, input, axis=1, num_axes=1, name=None):
        fluid = import_fluid()

        assert num_axes == 1, "layer scale not support this num_axes[%d] now" % (
            num_axes)

        prefix = name + '_'
        scale_shape = input.shape[axis:axis + num_axes]
        param_attr = fluid.ParamAttr(name=prefix + 'scale')
        scale_param = fluid.layers.create_parameter(
            shape=scale_shape, dtype=input.dtype, name=name, attr=param_attr)

        offset_attr = fluid.ParamAttr(name=prefix + 'offset')
        offset_param = fluid.layers.create_parameter(
            shape=scale_shape, dtype=input.dtype, name=name, attr=offset_attr)

        output = fluid.layers.elementwise_mul(input, scale_param, axis=axis)
        output = fluid.layers.elementwise_add(output, offset_param, axis=axis)
        return output

    def custom_layer_factory(self):
        """ get a custom layer maker provided by subclass
        """
        raise NotImplementedError(
            '[custom_layer_factory] must be implemented by the subclass.')

    @layer
    def custom_layer(self, inputs, kind, name, *args, **kwargs):
        """ make custom layer
        """
        layer_factory = self.custom_layer_factory()
        return layer_factory(kind, inputs, name, *args, **kwargs)


class AlexNet(Network):
    ### automatically generated by caffe2fluid ###
    inputs_info = {"rois": [5, 1, 1],"data": [3, 500, 500]}
    custom_layers_path = "/home/vis/wanglong03/paddle_gits/models.git.wallo/fluid/image_classification/caffe2fluid/kaffe"

    def custom_layer_factory(self):
        import os

        pk_paths = []
        default = os.path.dirname(os.path.abspath(__file__))
        location = os.environ.get('/home/vis/wanglong03/paddle_gits/models.git.wallo/fluid/image_classification/caffe2fluid/kaffe', default)
        pk_name = 'custom_layers'
        pk_dir = os.path.join(location, pk_name)
        pk_paths.append((location, pk_dir))

        location = AlexNet.custom_layers_path
        pk_dir = os.path.join(AlexNet.custom_layers_path, pk_name)
        pk_paths.append((location, pk_dir))

        for loc, pk_dir in pk_paths:
            if os.path.exists(pk_dir):
                if loc not in sys.path:
                    sys.path.insert(0, loc)
                    break

        try:
            from custom_layers import make_custom_layer
            return make_custom_layer
        except Exception as e:
            print('maybe you should set $/home/vis/wanglong03/paddle_gits/models.git.wallo/fluid/image_classification/caffe2fluid/kaffe first')
            raise e

    @classmethod
    def input_shapes(cls):
        return cls.inputs_info

    @classmethod
    def convert(cls, npy_model, fluid_path, outputs=None):
        fluid = import_fluid()
        shapes = cls.input_shapes()
        input_name = shapes.keys()[0]
        feed_data = {}
        for name, shape in shapes.items():
            data_layer = fluid.layers.data(
                name=name, shape=shape, dtype="float32")
            feed_data[name] = data_layer

        net = cls(feed_data)
        place = fluid.CPUPlace()
        exe = fluid.Executor(place)
        exe.run(fluid.default_startup_program())
        net.load(data_path=npy_model, exe=exe, place=place)
        output_vars = []

        model_filename = 'model'
        params_filename = 'params'
        if outputs is None:
            output_vars.append(net.get_output())
        else:
            if outputs[0] == 'dump_all':
                model_filename = None
                params_filename = None
                output_vars.append(net.get_output())
            else:
                if type(outputs) is list:
                    for n in outputs:
                        assert n in net.layers, 'not found layer with this name[%s]' % (
                            n)
                        output_vars.append(net.layers[n])

        fluid.io.save_inference_model(
            fluid_path, [input_name],
            output_vars,
            exe,
            main_program=None,
            model_filename=model_filename,
            params_filename=model_filename)
        return 0

    def setup(self):
        self.feed('data')
        self.conv(11, 11, 96, 4, 4, name='conv1')
        self.lrn(5, 2e-05, 0.75, name='norm1')
        self.max_pool(3, 3, 2, 2, True, name='pool1')
        self.conv(5, 5, 256, 1, 1, padding=[2, 2], group=2, name='conv2')
        self.lrn(5, 2e-05, 0.75, name='norm2')
        self.max_pool(3, 3, 2, 2, True, name='pool2')
        self.conv(3, 3, 384, 1, 1, padding=[1, 1], name='conv3')
        self.conv(3, 3, 384, 1, 1, padding=[1, 1], group=2, name='conv4')
        self.conv(3, 3, 64, 1, 1, padding=[1, 1], group=2, name='conv5_roi')

        self.feed('conv5_roi', 
                  'rois')
        self.custom_layer('ROIPooling', pooled_h=6, spatial_scale=0.06, pooled_w=6, name='roi_pool5')
        self.fc(256, name='rpn_fc')
        self.fc(2, relu=False, name='cls_score')
        self.softmax(name='cls_prob')

        self.feed('rpn_fc')
        self.fc(8, relu=False, name='bbox_pred')


def main():
    """ a tool used to convert caffe model to fluid
    """

    import sys
    import os
    filename = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    if len(sys.argv) < 3:
        print('usage:')
        print('	python %s %s.npy [save_dir] [layer names seperated by comma]' \
                % (sys.argv[0], filename))
        print('	eg: python %s %s.npy ./fluid' % (sys.argv[0], filename))
        print('	eg: python %s %s.npy ./fluid layer_name1,layer_name2' \
                % (sys.argv[0], filename))
        return 1

    npy_weight = sys.argv[1]
    fluid_model = sys.argv[2]
    outputs = None
    if len(sys.argv) >= 4:
        outputs = sys.argv[3].split(',')

    ret = AlexNet.convert(npy_weight, fluid_model, outputs)
    if ret == 0:
        outputs = 'last output layer' if outputs is None else outputs
        print('succeed to convert to fluid format with output layers[%s]'
              ' in directory[%s]' % (outputs, fluid_model))
    else:
        print('failed to convert model to fluid format')

    return ret


if __name__ == "__main__":
    exit(main())
