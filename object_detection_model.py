import numpy as np
import cv2
from keras.models import Model
from keras.layers import Input, Conv2D, Reshape, Lambda
from keras.applications.mobilenet import MobileNet
from box_utils import decode_netout, compute_overlap, compute_ap

class MobileNetFeatureExtractor:
    """
    A lightweight CNN for object detection, developed to run on resource constrained devices - 
    MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications
    Andrew G. Howard, Menglong Zhu, Bo Chen, Dmitry Kalenichenko, Weijun Wang, Tobias Weyand, Marco Andreetto, Hartwig Adam
    April 2017 [arXiv:1704.04861v1 [cs.CV]]
    https://arxiv.org/abs/1704.04861

    Implementation as a feature extractor adapted from:
    https://github.com/experiencor/keras-yolo2/blob/master/backend.py
    """

    def __init__(self, input_size):
        input_image = Input(shape=(input_size, input_size, 3))

        mobilenet = MobileNet(input_shape=(224,224,3), include_top=False)
        mobilenet.load_weights("data/mobilenet_backend.h5")
        x = mobilenet(input_image)

        self.feature_extractor = Model(input_image, x)  

    def normalize(self, image):
        image = image / 255.
        image = image - 0.5
        image = image * 2.
        return image

    def get_output_shape(self):
        return self.feature_extractor.get_output_shape_at(-1)[1:3]

    def extract(self, input_image):
        return self.feature_extractor(input_image)

class ObjectDetection(object):
    def __init__(self, backend,
                       input_size, 
                       labels,
                       max_box_per_image,
                       anchors):

        self.input_size = input_size
        self.labels   = list(labels)
        self.nb_class = len(self.labels)
        self.nb_box   = len(anchors)//2
        self.class_wt = np.ones(self.nb_class, dtype='float32')
        self.anchors  = anchors
        self.max_box_per_image = max_box_per_image

        # =======================================
        # Two inputs:
        #   1. image
        #   2. bounding box (training phase only)
        # =======================================

        input_image     = Input(shape=(self.input_size, self.input_size, 3))
        self.true_boxes = Input(shape=(1, 1, 1, max_box_per_image , 4))

        # ========================
        # Feature extraction layer
        # ========================

        self.feature_extractor = MobileNetFeatureExtractor(self.input_size)

        self.grid_h, self.grid_w = self.feature_extractor.get_output_shape()

        print("Output from feature extractor has shape:", self.grid_h, ",", self.grid_w) 
  
        features = self.feature_extractor.extract(input_image)            

        # ======================
        # Object detection layer
        # ======================

        MULT = 3 # increase the number of Convolutional filters, if the object classes prove harder to detect

        # tensor shape: (1, 7, 7, 1024)
        # intepretation: 7*7 grid of feature vectors describing each grid segment
        output = Conv2D(MULT * self.nb_box * (4 + 1 + self.nb_class), # 105 filters if MULT == 3
                        (1,1), strides=(1,1), 
                        padding='same', 
                        name='DetectionLayer', 
                        kernel_initializer='lecun_normal')(features)

        # tensor shape: (1, 7, 7, 105)
        # intepretation: 7*7 grid of bounding box predictions for each grid segment
        output = Reshape((self.grid_h, self.grid_w, self.nb_box, MULT * (4 + 1 + self.nb_class)))(output)

        # tensor shape: (1, 7, 7, 5, 21)
        output = Lambda(lambda args: args[0])([output, self.true_boxes]) # dummy layer (workaround for Keras "Exception: Layer is not connected")

        self.model = Model([input_image, self.true_boxes], output)

        # print a summary of the whole model
        self.model.summary()

    def load_weights(self, weight_path):
        self.model.load_weights(weight_path)
        
    def save_weights(self, weight_path):
        self.model.save_weights(weight_path)
        
    def save(self, path):
        self.model.save(path)
        
    def to_json(self, path):
        return self.model.to_json()

    def predict(self, image):
        image_h, image_w, _ = image.shape
        image = self.feature_extractor.normalize(image)

        input_image = image[:,:,::-1]
        input_image = np.expand_dims(input_image, 0)
        dummy_array = np.zeros((1,1,1,1,self.max_box_per_image,4))

        netout = self.model.predict([input_image, dummy_array])[0]
        boxes  = decode_netout(netout, self.anchors, self.nb_class)

        return boxes
