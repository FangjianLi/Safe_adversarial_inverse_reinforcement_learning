import tensorflow as tf
import gym

class Discriminator_CBF_total:
    def __init__(self, name: str,  env, lr, num_batches, weight_ratio = 0.5): 
        """
        :param env:
        Output of this Discriminator is reward for learning agent. Not the cost.
        Because discriminator predicts  P(expert|s,a) = 1 - P(agent|s,a).
        """

        discrete_env_check = isinstance(env.action_space, gym.spaces.discrete.Discrete)

        try:
            self.expert_s = tf.placeholder(dtype=tf.float32, shape=[None] + list(env.observation_space_shape))
            self.agent_s = tf.placeholder(dtype=tf.float32, shape=[None] + list(env.observation_space_shape))
        except AttributeError:
            self.expert_s = tf.placeholder(dtype=tf.float32, shape=[None] + list(env.observation_space.shape))
            self.agent_s = tf.placeholder(dtype=tf.float32, shape=[None] + list(env.observation_space.shape))
        # we also need to add a placeholder for the Q safety critic value
        self.expert_safety_q = tf.placeholder(dtype=tf.float32, shape=[None, 1])
        self.agent_safety_q = tf.placeholder(dtype=tf.float32, shape=[None, 1])
        # we also need to add the extra penalty item 
        self.extra_penalty = tf.placeholder(dtype=tf.float32, shape=())


        if discrete_env_check:
            self.expert_a = tf.placeholder(dtype=tf.int32, shape=[None])
            self.agent_a = tf.placeholder(dtype=tf.int32, shape=[None])
        else:
            self.expert_a = tf.placeholder(dtype=tf.float32, shape=[None] + list(env.action_space.shape))
            self.agent_a = tf.placeholder(dtype=tf.float32, shape=[None] + list(env.action_space.shape))
        self.expert_sa_p=tf.placeholder(dtype=tf.float32, shape=[None])
        self.agent_sa_p=tf.placeholder(dtype=tf.float32, shape=[None])

        with tf.variable_scope(name):
            self.scope = tf.get_variable_scope().name


            if discrete_env_check:
                expert_actions = tf.one_hot(self.expert_a, depth=env.action_space.n)
                expert_actions += tf.random_normal(tf.shape(expert_actions), mean=0.2, stddev=0.1,
                                                     dtype=tf.float32) / 1.2

                agent_actions = tf.one_hot(self.agent_a, depth=env.action_space.n)
                agent_actions += tf.random_normal(tf.shape(agent_actions), mean=0.2, stddev=0.1,
                                                    dtype=tf.float32) / 1.2
            else:
                expert_actions = self.expert_a #  +tf.random_normal(tf.shape(self.expert_a), mean=0, stddev=0.05, dtype=tf.float32)
                agent_actions = self.agent_a # + tf.random_normal(tf.shape(self.agent_a), mean=0, stddev=0.05, dtype=tf.float32)

            expert_s_a = tf.concat([self.expert_s, expert_actions], axis=1)
            agent_s_a = tf.concat([self.agent_s, agent_actions], axis=1)



            with tf.variable_scope('network') as network_scope:
                #the probability of the expert's (s,a) is from expert
                prob_1 = self.construct_network(input=expert_s_a, safety_q=self.expert_safety_q) # we also updated here

                network_scope.reuse_variables()  # share parameter, it can reuse the parameter within the parameter
                #the probability of the agent's (s,a) is from agent
                prob_2 = self.construct_network(input=agent_s_a, safety_q=self.agent_safety_q)

            with tf.variable_scope('loss'):
                p_expert = tf.squeeze(tf.clip_by_value(prob_1, 0, 1))
                d_expert= p_expert/(p_expert+self.expert_sa_p)
                loss_expert = tf.reduce_mean(tf.log(d_expert))

                p_agent = tf.squeeze(tf.clip_by_value(prob_2, 0, 1))
                d_agent=1-p_agent/(p_agent+self.agent_sa_p)

                loss_agent = tf.reduce_mean(tf.log(d_agent))
                loss = loss_expert + loss_agent 
                self.loss = -loss + weight_ratio*self.extra_penalty
                # this is the exact formulation of GAIL loss function of the discriminator
                tf.summary.scalar('discriminator', loss)
                
            d_net_trainable = self.get_trainable_variables()

            optimizer = tf.train.AdamOptimizer(learning_rate=lr/num_batches) #5e-5
            self.train_op = optimizer.minimize(self.loss, var_list=d_net_trainable)

            self.rewards = tf.log(p_agent/(p_agent+self.agent_sa_p)) - tf.log(1-p_agent/(p_agent+self.agent_sa_p))
            self.rewards_ep = tf.log(tf.clip_by_value(prob_2, 1e-10, 1))

    def construct_network(self, input, safety_q): # we need to modify this
        layer_1_a = tf.layers.dense(inputs=input, units=40, activation=tf.nn.relu, name='layer1a')
        # layer_2_a = tf.layers.dense(inputs=layer_1_a, units=48, activation=tf.nn.relu, name='layer2a')

        layer_1_b = tf.layers.dense(inputs=safety_q, units=24, activation=tf.nn.relu, name='layer1b')
        # layer_2_b = tf.layers.dense(inputs=layer_1_b, units=16, activation=tf.nn.relu, name='layer2b')
        

        layer_2 = tf.layers.dense(inputs=tf.concat([layer_1_a, layer_1_b], axis=1), units=64, activation=tf.nn.relu, name='layer2') #128
        layer_3 = tf.layers.dense(inputs=layer_2, units=64, activation=tf.nn.relu, name='layer3')
        prob = tf.layers.dense(inputs=layer_3, units=1, activation=tf.nn.sigmoid, name='prob')
        return prob  #the sigmoid is used to generate probability

    def train(self, expert_s, expert_a, agent_s, agent_a, expert_sa_p,agent_sa_p, expert_safety_q, agent_safety_q, extra_penalty):
        return tf.get_default_session().run([self.loss, self.train_op], feed_dict={self.expert_s: expert_s,
                                                                      self.expert_a: expert_a,
                                                                      self.agent_s: agent_s,
                                                                      self.agent_a: agent_a,
                                                                      self.expert_sa_p: expert_sa_p,
                                                                      self.agent_sa_p: agent_sa_p,
                                                                      self.expert_safety_q: expert_safety_q,
                                                                      self.agent_safety_q: agent_safety_q,
                                                                      self.extra_penalty: extra_penalty})

    def get_rewards(self, agent_s, agent_a, agent_sa_p, agent_safety_q):
        return tf.get_default_session().run(self.rewards, feed_dict={self.agent_s: agent_s,
                                                                     self.agent_a: agent_a,
                                                                     self.agent_sa_p: agent_sa_p,
                                                                     self.agent_safety_q: agent_safety_q})
    
    def get_rewards_ep(self, agent_s, agent_a, agent_safety_q):
        return tf.get_default_session().run(self.rewards_ep, feed_dict={self.agent_s: agent_s,
                                                                     self.agent_a: agent_a,
                                                                     self.agent_safety_q: agent_safety_q})
    
    
    

    def get_trainable_variables(self): #this might be used to design the regulator
        return tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, self.scope)