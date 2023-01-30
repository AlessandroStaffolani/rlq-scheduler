import logging
import torch
from torch import nn
from torch.nn import functional as F


class FullyConnected(torch.nn.Module):
    """
    Fully connected Neural Network, with 3 hidden layers that decrease the number of nodes for each subsequent hidden
    layer dividing the size of previous one by 2. As activation function is use ReLU function
    """

    def __init__(self, input_size, output_size, hidden_layers=2):
        """
        Model constructor
        Parameters
        ----------
        input_size: int
            input size of the network
        output_size: int
            output size of the network
        hidden_layers: int
            number of hidden layers to use
        """
        super(FullyConnected, self).__init__()
        self.hidden_layers = hidden_layers
        previous_layer_output = input_size
        # create hidden layers
        for i in range(self.hidden_layers):
            next_layer_input = int(previous_layer_output / 2)
            next_layer_input = next_layer_input if next_layer_input > 1 else 1
            setattr(self, 'hidden_{}'.format(str(i)), nn.Linear(previous_layer_output, next_layer_input))
            previous_layer_output = next_layer_input
        # finally add the output layer
        self.output = nn.Linear(previous_layer_output, output_size)

    def forward(self, x):
        # for each hidden layers
        for i in range(self.hidden_layers):
            # get the layer
            layer = getattr(self, 'hidden_{}'.format(str(i)))
            # apply ReLU activation function on the layer nodes
            x = layer(x)
            x = F.relu(x)
        # finally apply sigmoid activation function on the output nodes
        return self.output(x)

    def log_weights(self, logger: logging.Logger, level=logging.INFO, title=None):
        parameters = self.parameters()
        if title is not None:
            logger.log(level, title)
        logger.log(level, self)
        for i, param in enumerate(parameters):
            logger.log(level, f"Level {i} with shape: {param.shape} and values: {param.tolist()}")


class FullyConnectedDiamond(torch.nn.Module):

    def __init__(self, input_size, output_size):
        super(FullyConnectedDiamond, self).__init__()
        self.input_layer = nn.Linear(input_size, input_size * 2)
        self.hidden_layer_1 = nn.Linear(input_size * 2, input_size * 3)
        self.hidden_layer_2 = nn.Linear(input_size * 3, input_size * 2)
        self.hidden_layer_3 = nn.Linear(input_size * 2, input_size)
        self.dropout = nn.Dropout(p=0.5)
        self.output_layer = nn.Linear(input_size, output_size)

    def forward(self, x):
        x = F.relu(self.input_layer(x))

        x = self.dropout(F.relu(self.hidden_layer_1(x)))
        x = self.dropout(F.relu(self.hidden_layer_2(x)))
        x = self.dropout(F.relu(self.hidden_layer_3(x)))

        return self.output_layer(x)

    def log_weights(self, logger: logging.Logger, level=logging.INFO, title=None):
        parameters = self.parameters()
        if title is not None:
            logger.log(level, title)
        logger.log(level, self)
        for i, param in enumerate(parameters):
            logger.log(level, f"Level {i} with shape: {param.shape} and values: {param.tolist()}")


class QNetworkFactory:
    __available_networks = {
        'fully-connected': FullyConnected,
        'fc-diamond': FullyConnectedDiamond
    }

    @staticmethod
    def get_net(type_name, **kwargs):
        if type_name in QNetworkFactory.__available_networks:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            return QNetworkFactory.__available_networks[type_name](**kwargs).to(device)
        else:
            raise AttributeError('Q-Network {} not available. Try one of the available {}'
                                 .format(type_name, str(list(QNetworkFactory.__available_networks.keys()))))
