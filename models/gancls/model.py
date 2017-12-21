from utils.ops import *
from utils.utils import *


class GanCls(object):
    def __init__(self, cfg):
        """
        Args:
          cfg: Config specifying all the parameters of the model.
        """

        self.name = 'GANL_CLS'

        self.batch_size = cfg.TRAIN.BATCH_SIZE
        self.sample_num = cfg.TRAIN.SAMPLE_NUM

        self.output_size = cfg.MODEL.OUTPUT_SIZE

        self.z_dim = cfg.MODEL.Z_DIM
        self.embed_dim = cfg.MODEL.EMBED_DIM
        self.compressed_embed_dim = cfg.MODEL.COMPRESSED_EMBED_DIM

        self.gf_dim = cfg.MODEL.GF_DIM
        self.df_dim = cfg.MODEL.DF_DIM
        
        self.image_dims = [cfg.MODEL.IMAGE_SHAPE.H, cfg.MODEL.IMAGE_SHAPE.W, cfg.MODEL.IMAGE_SHAPE.D]

        self.build_model()

    def build_model(self):
        # Define the input tensor by appending the batch size dimension to the image dimension
        self.inputs = tf.placeholder(tf.float32, [self.batch_size] + self.image_dims, name='real_images')
        self.wrong_inputs = tf.placeholder(tf.float32, [self.batch_size] + self.image_dims, name='wrong_images')
        self.phi_inputs = tf.placeholder(tf.float32, [self.batch_size] + [self.embed_dim], name='phi_inputs')

        self.z = tf.placeholder(tf.float32, [self.batch_size, self.z_dim], name='z')

        self.z_sample = tf.placeholder(tf.float32, [self.sample_num] + [self.z_dim], name='z_sample')
        self.phi_sample = tf.placeholder(tf.float32, [self.sample_num] + [self.embed_dim], name='phi_sample')

        self.G = self.generator(self.z, self.phi_inputs, reuse=False)
        self.D_synthetic, self.D_synthetic_logits = self.discriminator(self.G, self.phi_inputs, reuse=False)
        self.D_real_match, self.D_real_match_logits = self.discriminator(self.inputs, self.phi_inputs, reuse=True)
        self.D_real_mismatch, self.D_real_mismatch_logits = self.discriminator(self.wrong_inputs, self.phi_inputs,
                                                                               reuse=True)
        self.sampler = self.generator(self.z_sample, self.phi_sample, is_training=False, reuse=True, sampler=True)

    def discriminator(self, inputs, phi, is_training=True, reuse=False):
        w_init = tf.random_normal_initializer(stddev=0.02)
        batch_norm_init = {
            'gamma': tf.random_normal_initializer(1., 0.02),
        }

        s16 = self.output_size / 16
        with tf.variable_scope("discriminator", reuse=reuse):
            net_ho = tf.layers.conv2d(inputs=inputs, filters=self.df_dim, kernel_size=(4, 4), strides=(2, 2),
                                      padding='same', activation=lambda l: tf.nn.leaky_relu(l, 0.2), 
                                      kernel_initializer=w_init,
                                      name='d_ho/conv2d')
            net_h1 = tf.layers.conv2d(inputs=net_ho, filters=self.df_dim * 2, kernel_size=(4, 4), strides=(2, 2),
                                      padding='same', activation=None, kernel_initializer=w_init,
                                      name='d_h1/conv2d')
            net_h1 = batch_normalization(net_h1, is_training=is_training, initializers=batch_norm_init,
                                         activation=lambda l: tf.nn.leaky_relu(l, 0.2), name='d_h1/batch_norm')
            net_h2 = tf.layers.conv2d(inputs=net_h1, filters=self.df_dim * 4, kernel_size=(4, 4), strides=(2, 2),
                                      padding='same', activation=None, kernel_initializer=w_init,
                                      name='d_h2/conv2d')
            net_h2 = batch_normalization(net_h2, is_training=is_training, initializers=batch_norm_init,
                                         activation=lambda l: tf.nn.leaky_relu(l, 0.2), name='d_h2/batch_norm')
            net_h3 = tf.layers.conv2d(inputs=net_h2, filters=self.df_dim * 8, kernel_size=(4, 4), strides=(2, 2),
                                      padding='same', activation=None, kernel_initializer=w_init,
                                      name='d_h3/conv2d')
            net_h3 = batch_normalization(net_h3, is_training=is_training, initializers=batch_norm_init,
                                         activation=None, name='d_h3/batch_norm')
            # --------------------------------------------------------

            # Residual layer
            net = tf.layers.conv2d(inputs=net_h3, filters=self.df_dim * 2, kernel_size=(1, 1), strides=(1, 1),
                                   padding='valid', activation=None, kernel_initializer=w_init,
                                   name='d_h4_res/conv2d')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=lambda l: tf.nn.leaky_relu(l, 0.2), name='d_h4_res/batch_norm')
            net = tf.layers.conv2d(inputs=net, filters=self.df_dim * 2, kernel_size=(3, 3), strides=(1, 1),
                                   padding='same', activation=None, kernel_initializer=w_init,
                                   name='d_h4_res/conv2d2')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=lambda l: tf.nn.leaky_relu(l, 0.2), name='d_h4_res/batch_norm2')
            net = tf.layers.conv2d(inputs=net, filters=self.df_dim * 8, kernel_size=(3, 3), strides=(1, 1),
                                   padding='same', activation=None, kernel_initializer=w_init,
                                   name='d_h4_res/conv2d3')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=None, name='d_h4_res/batch_norm3')
            net_h4 = tf.add(net_h3, net, name='d_h4/add')
            net_h4 = tf.nn.leaky_relu(net_h4, 0.2, name='d_h4/add_lrelu')
            # --------------------------------------------------------

            # Compress embeddings
            net_embed = tf.layers.dense(inputs=phi, units=self.compressed_embed_dim,
                                        activation=lambda l: tf.nn.leaky_relu(l, 0.2), name='d_net_embed')

            # Append embeddings in depth
            net_embed = tf.reshape(net_embed, [self.batch_size, 4, 4, -1])
            net_h4_concat = tf.concat([net_h4, net_embed], 3, name='d_h4_concat')

            net_h4 = tf.layers.conv2d(inputs=net_h4_concat, filters=self.df_dim * 8, kernel_size=(1, 1), strides=(1, 1),
                                      padding='valid', activation=None, kernel_initializer=w_init,
                                      name='d_h4_concat/conv2d')
            net_h4 = batch_normalization(net_h4, is_training=is_training, initializers=batch_norm_init,
                                         activation=lambda l: tf.nn.leaky_relu(l, 0.2), name='d_h4_concat/batch_norm')

            net_logits = tf.layers.conv2d(inputs=net_h4, filters=1, kernel_size=(s16, s16), strides=(s16, s16),
                                          padding='valid', kernel_initializer=w_init,
                                          name='d_net_logits')

            return tf.nn.sigmoid(net_logits), net_logits

    def generator(self, z, phi, is_training=True, reuse=False, sampler=False):
        w_init = tf.random_normal_initializer(stddev=0.02)
        batch_norm_init = {
            'gamma': tf.random_normal_initializer(1., 0.02),
        }

        s = self.output_size
        s2, s4, s8, s16 = int(s / 2), int(s / 4), int(s / 8), int(s / 16)
        with tf.variable_scope("generator", reuse=reuse):
            # Compress the embedding and append it to z
            net_embed = tf.layers.dense(inputs=phi, units=self.compressed_embed_dim, activation=None,
                                        name='g_net_embed')
            net_input = tf.concat([z, net_embed], 1, name='g_z_concat')

            net_h0 = tf.layers.dense(net_input, units=self.gf_dim*8*s16*s16, activation=None,
                                     kernel_initializer=w_init, name='g_h0/dense')
            net_h0 = batch_normalization(net_h0, is_training=is_training, initializers=batch_norm_init,
                                         activation=None, name='g_ho/batch_norm')
            # --------------------------------------------------------

            # Reshape based on the number of samples if this is the sampler (instead of the training batch_size).
            if sampler:
                net_h0 = tf.reshape(net_h0, [self.sample_num, s16, s16, -1], name='g_ho/reshape')
            else:
                net_h0 = tf.reshape(net_h0, [self.batch_size, s16, s16, -1], name='g_ho/reshape')

            # Residual layer
            net = tf.layers.conv2d(inputs=net_h0, filters=self.gf_dim * 2, kernel_size=(1, 1), strides=(1, 1),
                                   padding='valid', activation=None, kernel_initializer=w_init,
                                   name='g_h1_res/conv2d')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=tf.nn.relu, name='g_h1_res/batch_norm')
            net = tf.layers.conv2d(inputs=net, filters=self.gf_dim * 2, kernel_size=(3, 3), strides=(1, 1),
                                   padding='same', activation=None, kernel_initializer=w_init,
                                   name='g_h1_res/conv2d2')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=tf.nn.relu, name='g_h1_res/batch_norm2')
            net = tf.layers.conv2d(inputs=net, filters=self.gf_dim * 8, kernel_size=(3, 3), strides=(1, 1),
                                   padding='same', activation=None, kernel_initializer=w_init,
                                   name='g_h1_res/conv2d3')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=None, name='g_h1_res/batch_norm3')
            net_h1 = tf.add(net_h0, net, name='g_h1/add')
            net_h1 = tf.nn.relu(net_h1, name='g_h1/add_lrelu')
            # --------------------------------------------------------

            net_h2 = tf.layers.conv2d_transpose(net_h1, filters=self.gf_dim*4, kernel_size=(4, 4), strides=(2, 2),
                                                padding='same', activation=None, kernel_initializer=w_init,
                                                name='g_h2/deconv2d')
            net_h2 = tf.layers.conv2d(inputs=net_h2, filters=self.gf_dim*4, kernel_size=(3, 3), strides=(1, 1),
                                      padding='same', activation=None, kernel_initializer=w_init,
                                      name='g_h2/conv2d')
            net_h2 = batch_normalization(net_h2, is_training=is_training, initializers=batch_norm_init,
                                         activation=None, name='g_h2/batch_norm')
            # --------------------------------------------------------

            # Residual layer
            net = tf.layers.conv2d(inputs=net_h2, filters=self.gf_dim, kernel_size=(1, 1), strides=(1, 1),
                                   padding='valid', activation=None, kernel_initializer=w_init,
                                   name='g_h3_res/conv2d')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=tf.nn.relu, name='g_h3_res/batch_norm')
            net = tf.layers.conv2d(inputs=net, filters=self.gf_dim, kernel_size=(3, 3), strides=(1, 1),
                                   padding='same', activation=None, kernel_initializer=w_init,
                                   name='g_h3_res/conv2d2')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=tf.nn.relu, name='g_h3_res/batch_norm2')
            net = tf.layers.conv2d(inputs=net, filters=self.gf_dim*4, kernel_size=(3, 3), strides=(1, 1),
                                   padding='same', activation=None, kernel_initializer=w_init,
                                   name='g_h3_res/conv2d3')
            net = batch_normalization(net, is_training=is_training, initializers=batch_norm_init,
                                      activation=None, name='g_h3_res/batch_norm3')
            net_h3 = tf.add(net_h2, net, name='g_h3/add')
            net_h3 = tf.nn.relu(net_h3, name='g_h3/add_lrelu')
            # --------------------------------------------------------

            net_h4 = tf.layers.conv2d_transpose(net_h3, filters=self.gf_dim*2, kernel_size=(4, 4), strides=(2, 2),
                                                padding='same', activation=None, kernel_initializer=w_init,
                                                name='g_h4/deconv2d')
            net_h4 = tf.layers.conv2d(inputs=net_h4, filters=self.gf_dim*2, kernel_size=(3, 3), strides=(1, 1),
                                      padding='same', activation=None, kernel_initializer=w_init,
                                      name='g_h4/conv2d')
            net_h4 = batch_normalization(net_h4, is_training=is_training, initializers=batch_norm_init,
                                         activation=tf.nn.relu, name='g_h4/batch_norm')

            net_h5 = tf.layers.conv2d_transpose(net_h4, filters=self.gf_dim, kernel_size=(4, 4), strides=(2, 2),
                                                padding='same', activation=None, kernel_initializer=w_init,
                                                name='g_h5/deconv2d')
            net_h5 = tf.layers.conv2d(inputs=net_h5, filters=self.gf_dim, kernel_size=(3, 3), strides=(1, 1),
                                      padding='same', activation=None, kernel_initializer=w_init,
                                      name='g_h5/conv2d')
            net_h5 = batch_normalization(net_h5, is_training=is_training, initializers=batch_norm_init,
                                         activation=tf.nn.relu, name='g_h5/batch_norm')

            net_logits = tf.layers.conv2d_transpose(net_h5, filters=self.image_dims[-1], kernel_size=(4, 4),
                                                    strides=(2, 2), padding='same', activation=None,
                                                    kernel_initializer=w_init, name='g_logits/deconv2d')
            net_logits = tf.layers.conv2d(inputs=net_logits, filters=self.image_dims[-1], kernel_size=(3, 3),
                                          strides=(1, 1), padding='same', activation=None,
                                          kernel_initializer=w_init, name='g_logits/conv2d')

            net_output = tf.nn.tanh(net_logits)
            return net_output
