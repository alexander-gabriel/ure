from opencog.atomspace import AtomSpace, types, Atom, Handle, TruthValue, types as t
import opencog.cogserver
from tree import *
import adaptors
from util import *
from itertools import *
import sys

# unit of timestamps is 0.01 second so multiply by 100
interval = 100* 20

def pairwise(iterable):
    """
    s -> (s0,s1), (s1,s2), (s2, s3), ...

    >>> list(pairwise((1,2,3,4)))
    [(1, 2), (2, 3), (3, 4)]
    """
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)

class Fishgram:
    def __init__(self,  atomspace):
        self.forest = adaptors.ForestExtractor(atomspace,  None)
        # settings
        self.min_embeddings = 3
        self.min_frequency = 0.5
        self.atomspace = atomspace
        
        self.max_per_layer = 1e9 # 10 # 1e35 # 600

    def run(self):
        self.forest.extractForest()

#        print '# predicates(1arg) including infrequent:', len(self.forest.tree_embeddings[1])
#        self.forest.tree_embeddings[1] = dict([(tree, argslist_set)
#                                               for (tree, argslist_set) in self.forest.tree_embeddings[1] .items()
#                                               if len(argslist_set) >= self.min_embeddings])
#        unary_conjunctions = dict([((tree, ), argslist_set) for (tree, argslist_set) in self.forest.tree_embeddings[1].items()])
#
#        print '# predicates(1arg):', len(unary_conjunctions)
        #return self.add_all_predicates_1var(unary_conjunctions)

        #return self.add_all_predicates_1var_dfs()
        return [layer for layer in self.closed_bfs_layers()]

    def iterated_implications(self):
        """Find implications, starting with maximum support (i.e. maximum pruning in the search for
        frequent subgraphs). Then lower the support incrementally."""
#        self.min_embeddings = 77
#        
#        while self.min_embeddings > 0:
#            print "support =", self.min_embeddings
#            self.implications()
#            self.min_embeddings -= 5
        while self.min_frequency > 0.00000000001:
            print '\n\x1B[1;32mfreq =', self.min_frequency, '\x1B[0m'
            self.implications()
            self.min_frequency /= 2

    def implications(self):
        layers = []
        for layer in self.closed_bfs_layers():
            
            #for conj, embs in layer:
            #    print pp(conj), pp(embs)
            
            layers.append(layer)
            if len(layers) >= 2:
                self.output_implications_for_last_layer(layers)

# breadth-first search (to make it simpler!)
# use the extension list.
# prune unclosed conjunctions.
# you only need to add extensions if they're in the closure.

    def closed_bfs_extend_layer(self, prev_layer):
        #next_layer_iter = self.extensions(prev_layer)
        next_layer_iter = self.extensions_simple(prev_layer)
        return self.prune_frequency(next_layer_iter)
        return next_layer_iter

    def closed_bfs_layers(self):
        """Main function to run the breadth-first search. It yields results one layer at a time. A layer
        contains all of the conjunctions resulting from extending previous conjunctions with one extra
        tree. For some purposes it would be better to return results immediately rather than one layer at
        a time, however creating ImplicationLinks requires previous layers."""
        #all_bindinglists = [(obj, ) for obj in self.forest.all_objects]
        #prev_layer = [((), None )]
        prev_layer = [((), [{}] )]

        while len(prev_layer) > 0:
            # Mixing generator and list style because future results depend on previous results.
            # It's less efficient with memory but still allows returning results sooner.
            new_layer = [conj_embs for conj_embs in self.closed_bfs_extend_layer(prev_layer)]
            
            if len(new_layer):
                conj_length = len(new_layer[0][0])
                #print '\x1B[1;32m# Conjunctions of size', conj_length,':', len(new_layer), 'pruned', pruned,'\x1B[0m'
                print '\x1B[1;32m# Conjunctions of size', conj_length, ':', len(new_layer), '\x1B[0m'
                yield new_layer

            prev_layer = new_layer


    def _create_new_variables(self, tr, embeddings):
        sa_mapping = {}
        tr = standardize_apart(tr, sa_mapping)
        
        rebound_embs = []
        for s in embeddings:
            s2 = {}
            for (old_var, new_var) in sa_mapping.items():
                obj = s[old_var]
                s2[new_var] = obj
            rebound_embs.append(s2)
        
        return tr, rebound_embs

    def _map_to_existing_variables(self, prev_binding, new_binding):
        # In this binding, a variable in the tree might fit an object that is already used.
        new_vars = [var for var in new_binding if var not in prev_binding]
        remapping = {}
        new_s = dict(prev_binding)
        for var in new_vars:
            obj = new_binding[var]
            tmp = [(o, v) for (v, o) in prev_binding.items() if o == obj]
            assert len(tmp) < 2
            if len(tmp) == 1:
                _, existing_variable = tmp[0]
                remapping[var] = existing_variable
            else:
                # If it is not a redundant var, then add it to the new binding.
                new_s[var] = obj

            # Never allow links that point to the same object twice
            tmp = [(o, v) for (v, o) in new_binding.items() if o == obj]
            if len(tmp) > 1:
                return None
        
        return remapping, new_s

    def _add_all_seq_and_links(self, conj, embedding):
        '''Takes a conjunction (with variables as usual) and an embedding (i.e. substitution). Returns the conjunction
        but with all possible SequentialAndLinks between variables. That is, if t2 and t1 are in the substitution, and
        t2 is shortly after t1, then the relevant variables will be connected by a new SequentialAndLink (if it hasn't been
        added previously).'''
        
        new_conj = conj[:]
        
        times_vars = [(obj, var) for (var, obj) in embedding.items()
                      if obj.t == t.TimeNode]
        times_vars = [(int(obj.name), var) for obj, var in times_vars]
        times_vars.sort()

        for (i, (t1, var1)) in enumerate(times_vars[:-1]):
            for (t2, var2) in times_vars[i+1:]:
                if 0 < t2 - t1 <= interval:
                    seq_and = tree("SequentialAndLink",  var1, var2)
                    if seq_and not in conj:
                        new_conj+=(seq_and,)
                else:
                    break
        
        return new_conj


    def extensions_simple(self, prev_layer):
        new_layer = []
        
        # Not correct - it must choose variables so that new 'links' (trees) will be connected in the right place.
        # That should be done based on embeddings (i.e. add a link if some of the embeddings have it)
        
        # But wait, you can just look it up and then merge new variables that point to existing objects.
        for (prev_conj,  prev_embeddings) in prev_layer:

            for tr_, embs_ in self.forest.tree_embeddings.items():
                # Give the tree new variables. Rewrite the embeddings to match.
                tr, rebound_embs = self._create_new_variables(tr_, embs_)

                extensions_for_prev_conj_and_tree_type = {}
                
                # They all have the same 'link label' (tree) but may be in different places.
                for s in rebound_embs:
                    for e in prev_embeddings:
                        # for each new var, if the object is in the previous embedding, then re-map them.
                        
                        tmp = self._map_to_existing_variables(e, s)
                        if tmp == None:
                            continue
                        remapping, new_s = tmp

                        remapped_tree = subst(remapping, tr)
                        remapped_conj = prev_conj+(remapped_tree,)
                        
                        # Simple easy approach: just add all possible SequentialAndLinks
                        remapped_conj_plus = self._add_all_seq_and_links(remapped_conj, new_s)

                        # Skip 'links' where there is no remapping, i.e. no connection to the existing pattern (no variables in common).
                        if ( prev_conj != () and
                                not len(remapping) and len(remapped_conj_plus) == len(remapped_conj) ):
                            continue

                        if remapped_tree in prev_conj:
                            continue
                        # Check for other equivalent ones. It'd be possible to reduce them (and increase efficiency) by ordering
                        # the extension of patterns. This would only work with a stable frequency measure though.
                        clones = [c for c in extensions_for_prev_conj_and_tree_type
                                   if c != remapped_conj_plus and
                                   unify(remapped_conj_plus, c, {}, True) != None]
                        if len(clones):
                            continue

                        if remapped_conj_plus not in extensions_for_prev_conj_and_tree_type:
                            extensions_for_prev_conj_and_tree_type[remapped_conj_plus] = []
                        extensions_for_prev_conj_and_tree_type[remapped_conj_plus].append(new_s)

                new_layer += extensions_for_prev_conj_and_tree_type.items()
        
        return new_layer


    def extending_links(self, binding):
        ret = set()
        
        for obj in binding:
            for predsize in sorted(self.forest.incoming[obj].keys()):
                #if predsize > 1: continue
                for slot in sorted(self.forest.incoming[obj][predsize].keys()):
                    for tree_id in self.forest.incoming[obj][predsize][slot]:
                        if tree_id not in ret:
                            ret.add(tree_id)
         
        return ret

    def extensions(self,  prev_layer):
        """Find all extensions for that fragment. An extension means adding one link to a particular
        node in the fragment. Nodes in the fragment are numbered from 0 onwards, and the numbers
        don't correspond to exact nodes in the AtomSpace. Each fragment has 1 or more embeddings,
        that is, matching sets of nodes/links in the AtomSpace."""
        # for each embedding
        # for each extension
        # add the new embedding to the set for that extension
        
        # new_layer is used to avoid redundancy. res keeps track of the smallest sets of results that can be returned at one time
        # (i.e. for which we can guarantee there won't be any further embeddings found later)
        new_layer = {}
        
        skipped = 0
        redundant_anyway = 0
        for (prev_conj,  prev_embeddings) in prev_layer:
            
            if len(new_layer) > self.max_per_layer:
                break

            # Results for extending this conjunction. All results for this conjunction are produced in this iteration.
            res = {}

            # Start with all single objects. The binding for no condition (empty tuple) is undefined. The algorithm
            # will create bindings for one-condition conjunctions and all other ones, by adding new variables when
            # necessary.
            if prev_conj == ():
                source_bindings = [(obj, ) for obj in self.forest.all_objects]
            else:
                source_bindings = prev_embeddings
            for emb in source_bindings:
                extension_tree_ids = self.extending_links(emb)

                if prev_conj == ():
                    emb = []

                #extension_tree_ids_sorted = sorted(extension_tree_ids,  key=lambda id: self.forest.all_trees[id])
                # If you sort the tree_ids by what bound-tree they are then you can return results more incrementally
                for tree_id in extension_tree_ids:

                    # Using the particular tree-instance, find its outgoing set
                    bindings = self.forest.bindings[tree_id]
                    # WRONG as the embedding for () is [every] one object
                    #i = len(emb)
                    # The number of the first available variable
                    i = len(get_varlist(prev_conj))
                    # The mapping from the (abstract) tree to node numbers in this conjunction            
                    s = {}
                    # Since we allow N-ary patterns, it could be connected to any number (>=1) of
                    # nodes in the conjunction so far, and 0+ new ones
                    new_embedding = copy(emb)
                    for slot in xrange(len(bindings)):
                        obj = bindings[slot]
                        
                        if obj in emb:
                            s[tree(slot)] = tree(emb.index(obj))
                            assert len(s) <= len(bindings)
                        else:
                            s[tree(slot)] = tree(i)
                            tmp = list(new_embedding)
                            tmp.append(obj)
                            new_embedding = tuple(tmp)
                            assert obj == new_embedding[i]
                            i+=1
                            assert len(s) <= len(bindings)

                    assert len(s) == len(bindings)

                    # After completing the substitution...
                    tr = self.forest.all_trees[tree_id]
                    bound_tree = subst(s, tr)

                    # Add this embedding for this bound tree.
                    # Bound trees contain variable numbers = the numbers inside the fragment                            
                    if bound_tree not in prev_conj:
                    #if self.after_conj(bound_tree,  prev_conj):
                        new_conj = prev_conj+(bound_tree,)
                        # Sort the bound trees in the conjunction. So e.g.  ((TreeB 1 2) (TreeA 1 3))  becomes  ((TreeA 1 3) (TreeB 1 2))
                        # This ensures that only one ordering is produced (out of the many possible orderings).
                        # If we assume breadth-first search it's possible to just do it here, because all the conjunctions of the same length
                        # are produced at the same time.
                        sc = tuple(sorted(new_conj))
                        #if sc != new_conj: print self.conjunction_to_string(new_conj), "=>", self.conjunction_to_string(sc)                    

                        if sc == new_conj:
                            if sc not in new_layer:
                                new_layer[sc] = []
                                res[sc] = []
                            
                                clones = [c for c in new_layer if unify(new_conj, c, {}, True) != None and c != sc]
                                if len(clones): # other copies besides itself
                                    print "REDUNDANCY", pp(new_conj), len(clones)-1
                                    redundant_anyway+=1
                                
                            new_embedding = tuple(new_embedding)
                            # BUG
                            assert len(new_embedding) == len(get_varlist(new_conj))
                            # TODO Don't include the same embedding multiple times. Why is it found multiple times? sc can be found multiple times?
                            if new_embedding not in new_layer[sc]:
                                new_layer[sc].append(new_embedding)                            
                                res[sc].append(new_embedding)
                            #print self.conjunction_to_string(new_conj), ":", len(new_layer[new_conj]), "so far"
                        else:
                            skipped+= 1
                
            # Yield the results (once you know they aren't going to be changed...)
            for conj_emb_pair in res.items():
                yield conj_emb_pair

        print "[skipped", skipped, "conjunction-embeddings that were only reorderings]", redundant_anyway, "redundant anyway", 
        #return new_layer.items()
        # Stops iteration at the end of the function
        
#        # Can't just use new_layer.items() because we want one entry for each conjunction (plus all of its embeddings)
#        return [(conj, new_layer[conj]) for conj in new_layer]

    def prune_frequency(self, layer):
        for (conj, embeddings) in layer:
            
            count = len(embeddings)*1.0
            num_possible_objects = len(self.forest.all_objects)*1.0
            num_variables = len(get_varlist(conj))*1.0
            
            normalized_frequency =  count / num_possible_objects ** num_variables
            if len(embeddings) >= self.min_embeddings:
            #if normalized_frequency > self.min_frequency:
                #print pp(conj), normalized_frequency
                yield (conj, embeddings)

    def conjunction_to_string(self,  conjunction):
        return str(tuple([str(tree) for tree in conjunction]))

    def outputConceptNodes(self, layers):
        id = 1001
        
        for layer in layers:
            for (conj, embs) in layer:
                if (len(get_varlist(conj)) == 1):
                    concept = self.atomspace.add_node(t.ConceptNode, 'fishgram_'+str(id))
                    id+=1
                    print concept
                    for tr in conj:
                        s = {tree(0):concept}
                        bound_tree = subst(s, tr)
                        #print bound_tree
                        print atom_from_tree(bound_tree, self.atomspace)

    def outputPredicateNodes(self, layers):
        id = 9001
        
        for layer in layers:
            for (conj, embs) in layer:
                predicate = self.atomspace.add_node(t.PredicateNode, 'fishgram_'+str(id))
                id+=1
                #print predicate
                
                vars = get_varlist(conj)
                #print [str(var) for var in vars]

                evalLink = tree('EvaluationLink',
                                    predicate, 
                                    tree('ListLink', vars))
                andLink = tree('AndLink',
                                    conj)
                
                qLink = tree('ForAllLink', 
                                tree('ListLink', vars), 
                                tree('ImplicationLink',
                                    andLink,
                                    evalLink))
                a = atom_from_tree(qLink, self.atomspace)
                
                a.tv = TruthValue(1, 10.0**9)
                count = len(embs)
                #eval_a = atom_from_tree(evalLink, self.atomspace)
                #eval_a.tv = TruthValue(1, count)
                
                print a

#                for tr in conj:
#                    s = {tree(0):concept}
#                    bound_tree = subst(s, tr)
#                    #print bound_tree
#                    print atom_from_tree(bound_tree, self.atomspace)

    def output_implications_for_last_layer(self, layers):
        if len(layers) < 2:
            return
        layer = layers[-1]
        prev_layer = layers[-2]
        for (conj, embs) in layer:

            vars = get_varlist(conj)
            #print [str(var) for var in vars]
            
            assert all( [len(vars) == len(binding) for binding in embs] )
            
            for i in xrange(0, len(conj)):
                conclusion = conj[i]
                premises = conj[:i] + conj[i+1:]
                
                # All SequentialAndLinks must be in the premises. Otherwise it might get weird.
                if conclusion.get_type() == t.SequentialAndLink:
                    continue
                
                # Let's say P implies Q. To keep things simple, P&Q must have the same number of variables as P.
                # In other words, the conclusion can't add extra variables. This would be equivalent to proving an
                # AverageLink (as the conclusion of the Implication).
                if not (len(get_varlist(conj)) == len(get_varlist(premises))):
                    continue
                
                # Fishgram won't produce conjunctions with dangling SeqAndLinks. And 
                # i.e. AtTime 1 eat;    SeqAnd 1 2
                # with 2 being a variable only used in the conclusion (and the whole conjunction), not in the premises.
                # The embedding count is undefined in this case.
                # Also, the count measure is not monotonic so if ordering were used you would sometimes miss things.
                try:
                    ce_premises = next(ce for ce in prev_layer if unify(premises, ce[0], {}, True) != None)
                    premises_original, premises_embs = ce_premises
                
#                        ce_conclusion = next(ce for ce in layers[0] if unify( (conclusion,) , ce[0], {}, True) != None)
#                        conclusion_original, conclusion_embs = ce_conclusion
                except StopIteration:
                    #sys.stderr.write("\noutput_implications_for_last_layer: didn't create required subconjunction"+
                    #    " due to either pruning issues or dangling SeqAndLinks\n"+str(premises)+'\n'+str(conclusion)+'\n')
                    continue

#                print map(str, premises)
#                print ce_premises[0]
#                print len(premises_embs), len(embs)
                
#                c_norm = normalize( (conj, emb), ce_conclusion )
#                p_norm = normalize( (conj, emb), ce_premises )
#                print p_norm, c_norm

##                # Use the embeddings lookup system (alternative approach)
##                premises_embs = self.forest.lookup_embeddings(premises)
##                embs = self.forest.lookup_embeddings(conj)
##                # Can also measure probability of conclusion by itself
                
                count_conj = len(embs)
                
                self.make_implication(premises, conclusion, len(premises_embs), count_conj)

    def make_implication(self, premises, conclusion, premises_support, conj_support):
        # Called the "confidence" in rule learning literature
        freq =  conj_support*1.0 / premises_support
#                count_unconditional = len(conclusion_embs)
#                surprise = conj_support / count_unconditional
        
        if freq > 0.00: # 0.05:
            assert len(premises)
            
            # Convert it into a Psi Rule. Note that this will remove variables corresponding to the TimeNodes, but
            # the embedding counts will still be equivalent.
            tmp = self.make_psi_rule(premises, conclusion)
            #tmp = (premises, conclusion)
            if tmp:
                (premises, conclusion) = tmp
                
                vars = get_varlist( premises+(conclusion,) )
                
                andLink = tree('SequentialAndLink',
                                    list(premises)) # premises is a tuple remember
                
                #print andLink

                qLink = tree('ForAllLink', 
                                tree('ListLink', vars), 
                                tree('ImplicationLink',
                                    tree('AndLink',        # Psi rule "meta-and"
                                        tree('AndLink'),  # Psi rule context
                                        andLink),             # Psi rule action
                                    conclusion)
                                )
                a = atom_from_tree(qLink, self.atomspace)
                
                a.tv = TruthValue( freq , premises_support )
                a.out[1].tv = TruthValue( freq , premises_support ) # PSI hack
                #count = len(embs)
                #eval_a = atom_from_tree(evalLink, self.atomspace)
                #eval_a.tv = TruthValue(1, count)
                
                print 'make_implication => %s' % (a,)
        else:
            print 'freq = %s' % freq
        
        if not conj_support <= premises_support:
            import pdb; pdb.set_trace()
        assert conj_support <= premises_support

    def make_psi_rule(self, premises, conclusion):
        tr = tree
        a = self.atomspace.add
        t = types
        
        time1 = new_var()
        time2 = new_var()
        action = new_var()
        goal = new_var()
        
        action_template = tr('AtTimeLink', time1,
                                tr('EvaluationLink',
                                    a(t.PredicateNode, name='actionDone'),
                                    tr('ListLink', 
                                       action
                                     )
                                )
                            )
        seq_and_template = tr('SequentialAndLink', time1, time2)
        increase_template = tr('AtTimeLink',
                     time2,
                     tr('EvaluationLink',
                                a(t.PredicateNode, name='increased'),
                                tr('ListLink', goal)
                                )
                     )

        ideal_premises = (action_template, seq_and_template)
        ideal_conclusion = increase_template

        s2 = unify(ideal_premises, premises, {})
        #print 'make_psi_rule: s2=%s' % (s2,)
        s3 = unify(ideal_conclusion, conclusion, s2)
        #print 'make_psi_rule: s3=%s' % (s3,)
        
        if s3 != None:
            #premises2 = [x for x in premises if not unify (seq_and_template, x, {})]
            action_psi = s3[action]
            # TODO should probably record the EvaluationLink in the increased predicate.
            goal_eval = s3[goal]
            
            premises2 = (action_psi, )

            return premises2, goal_eval
        else:
            return None

    def lookup_causal_patterns(self):
        tr = tree
        a = self.atomspace.add
        t = types
        
        time1 = new_var()
        time2 = new_var()
        action = new_var()
        goal = new_var()
        
        action_template = tr('AtTimeLink', time1,
                                tr('EvaluationLink',
                                    a(t.PredicateNode, name='actionDone'),
                                    tr('ListLink', 
                                       action
                                     )
                                )
                            )
        seq_and_template = tr('SequentialAndLink', time1, time2)
        increase_template = tr('AtTimeLink',
                     time2,
                     tr('EvaluationLink',
                                a(t.PredicateNode, name='increased'),
                                tr('ListLink', goal)
                                )
                     )

#        ideal_premises = (action_template, seq_and_template)
#        ideal_conclusion = increase_template
        
        self.causality_template = (action_template, increase_template, seq_and_template)
        
        # Try to find suitable patterns and then use them.
        print pp(self.causality_template)
        matches = find_matching_conjunctions(self.causality_template, self.forest.tree_embeddings.keys())
        
        for m in matches:
#            print pp(m.conj)
#            print pp(m.subst)
#            embs = self.forest.lookup_embeddings(m.conj)
#            print pp(embs)
            yield m.conj

    def make_all_psi_rules(self):
        for conj in self.lookup_causal_patterns():
            vars = get_varlist(conj)
            print "make_all_psi_rules: %s" % (pp(conj),)
            
            for (premises, conclusion) in self._split_conj_into_rules(conj):
                if not (len(get_varlist(conj)) == len(get_varlist(premises))):
                    continue
                
                # Filter it now since lookup_embeddings is slow
                if self.make_psi_rule(premises, conclusion) == None:
                    continue
   
                embs_conj = self.forest.lookup_embeddings(conj)
                embs_premises = self.forest.lookup_embeddings(premises)
   
                count_conj = len(embs_conj)
                count_premises = len(embs_premises)
                
                if count_conj > count_premises:
                    import pdb; pdb.set_trace()
                
                print "make_implication(premises=%s, conclusion=%s, count_premises=%s, count_conj=%s)" % (premises, conclusion, count_premises, count_conj)                
                if count_premises > 0:
                    self.make_implication(premises, conclusion, count_premises, count_conj)
    
    def _split_conj_into_rules(self, conj):
        for i in xrange(0, len(conj)):
            conclusion = conj[i]
            premises = conj[:i] + conj[i+1:]
            
            # Let's say P implies Q. To keep things simple, P&Q must have the same number of variables as P.
            # In other words, the conclusion can't add extra variables. This would be equivalent to proving an
            # AverageLink (as the conclusion of the Implication).
            if (len(get_varlist(conj)) == len(get_varlist(premises))):
                yield (premises, conclusion)


    def make_psi_rule_alt(self, premises_, conclusion_):
        """Looks for a suitable combination of conditions to make a Psi Rule. Returns premises and conclusions for the Psi Rule."""
        # Remove the (one!) SequentialAnd
        # convert AtTime by itself
        # convert Eval-actionDone
        
        # Because modifying inputs is evil
        premises, conclusion = list(premises_), conclusion_
        
        a = self.atomspace.add
        
        seq_and_template = tree('SequentialAndLink', -1, -2) # two TimeNodes
        time_template = tree('AtTimeLink', -1, -2) # 1 is a TimeNode, 2 is an EvaluationLink
        action_template = tree('EvaluationLink',
                                                a(t.PredicateNode, name='actionDone'),
                                                tree('ListLink', -1)) # -1 is the ExecutionLink for the action
        
#        res = tree('AtTimeLink',
#             time2_atom, 
#             tree('EvaluationLink',
#                        a(t.PredicateNode, name='increase'),
#                        tree('ListLink', -3)
#                        )
#             )
        
        # Can currently only handle one thing following another, not a series (>2)
        seq_ands_prem = [ x for x in premises if unify(seq_and_template, x, {}) != None ]
        actions_prem = [ x for x in premises if unify(action_template, x, {}) != None ]
        conc_is_atTime = unify(time_template, conclusion, {}) != None

        if 1 == len( seq_ands_prem ) and 1 == len(actions_prem): # and conc_is_atTime:
            premises.remove(seq_ands_prem[0])
            
            premises = [ self.replace(time_template, x, -2) for x in premises ]
            premises = [ self.replace(action_template, x, -1) for x in premises ]
            
            conclusion = replace(time_template, conclusion, -2)
            conclusion = replace(action_template, conclusion, -1)
        
            return tuple(premises), conclusion
        else:
            return None

    def replace(self, pattern, example, var):
        s = unify(pattern, example, {})
        if s != None:
            return s[tree(var)]
        else:
            return example
    
    def none_filter(self, list):
        return [x for x in list if x != None]

    # Wait, we need count(  P(X,Y) ) / count( G(X,Y). Not equal to count( P(X) * count(Y in G))
    def normalize(self, big_conj_and_embeddings, small_conj_and_embeddings):
        """If you take some of the conditions (trees) from a conjunction, the result will sometimes
        only refer to some of the variables. In this case the embeddings stored for that sub-conjunction
        will only include objects mentioned by the smaller conjunction. This function normalizes the
        count of embeddings. Suppose you have F(X,Y) == G(X, Y) AND H(X). The count for H(X) will be
        too low and you really need the count of "H(X) for all X and Y". This function will multiply the count
        by the number of objects in Y."""""
        big_conj, big_embs = big_conj_and_embeddings
        small_conj, small_embs = small_conj_and_embeddings
        
        # Count the number of possibilities for each variable. (Only possibilities that actually occur.)
        numvars = len(big_embs[0])
        var_objs = [set() for i in xrange(numvars)]
        
        for i in xrange(0, len(numvars)):
            for emb in big_embs:
                obj = emb[i]
                var_objs[i].add(obj)
        
        var_numobjs = [len(objs) for objs in var_objs]
        
        varlist_big = sorted(get_varlist(big_conj))
        varlist_small = sorted(get_varlist(small_conj))
        missing_vars = [v for v in varlist_big if v not in varlist_small]
        
        # the counts of possible objects for each variable missing in the smaller conjunction.
        numobjs_missing = [var_numobjs[v] for v in missing_vars]
        
        implied_cases = reduce(op.times, numobjs_missing, 1)
        
        return len(small_embs) * implied_cases

def make_seq(atomspace):
    times = atomspace.get_atoms_by_type(t.TimeNode)
    times = [f for f in times if f.name != "0"] # Related to a bug in the Psi Modulator system
    times = sorted(times, key= lambda t: int(t.name) )
    
    for time_atom in times:
        print time_atom.name

    for (i, time_atom) in enumerate(times[:-1]):
        t1 = int(time_atom.name)
        for time2_atom in times[i+1:]:
            t2 = int(time2_atom.name)
            if 0 < t2 - t1 <= interval:
                print atomspace.add_link(t.SequentialAndLink,  [time_atom,  time2_atom], TruthValue(1, 1))
            else:
                break

# Only works if DemandGoals are updated every cycle ( == every timestamp). The new version is similarly fast.
#def notice_changes_alt(atomspace):
#    tv_delta = 0.001
#    a = atomspace.add
#    
#    times = atomspace.get_atoms_by_type(t.TimeNode)
#    times = [f for f in times if f.name != "0"] # Related to a bug in the Psi Modulator system
#    times = sorted(times, key= lambda t: int(t.name) )
#
#    print len(times)
#
#    target_PredicateNodes = [x for x in atomspace.get_atoms_by_type(t.PredicateNode) if "DemandGoal" in x.name]
#
#    for atom in target_PredicateNodes:
#        target = tree('EvaluationLink', atom, new_var())
#        
#        for (i, time_atom) in enumerate(times[:-1]):
#            #time2_atom = times[i+1]
#            
#            template = tree('AtTimeLink', time_atom, target)
#            matches =[x for x in time_atom.incoming if unify(template, tree_from_atom(x), {}) != None]
#            
#            if len(matches) != 1:
#                continue
#            
#            template2 = tree('AtTimeLink', time2_atom, target)
#            matches2 =[x for x in time2_atom.incoming if unify(template2, tree_from_atom(x), {}) != None]
#
#            if len(matches2) == 1:
#                
#                tv1 = matches[0].tv
#                tv2 = matches2[0].tv
#                
#                print target, tv2-tv1
#                
#                if tv2 - tv1 > tv_delta:
#                    # increased
#                    pred = 'increased'
#                elif tv1 - tv2 > tv_delta:
#                    # decreased
#                    pred = 'decreased'
#                else:
#                    continue
#
#                print matches[0], matches2[0]
#
#                tv = TruthValue(1, 1e35)
#                res = tree('AtTimeLink',
#                         time2_atom, 
#                         tree('EvaluationLink',
#                                    a(t.PredicateNode, name=pred),
#                                    tree('ListLink', target)
#                                    )
#                         )
#                a = atom_from_tree(res, atomspace)
#                a.tv = tv
#                
#                print str(a)
#            else:
#                print '[no match]'

#def notice_changes_alt2(atomspace):
#    tv_delta = 0.01
#    
#    times = atomspace.get_atoms_by_type(t.TimeNode)
#    times = [f for f in times if f.name != "0"] # Related to a bug in the Psi Modulator system
#    times = sorted(times, key= lambda t: int(t.name) )
#
#    target_PredicateNodes = [x for x in atomspace.get_atoms_by_type(t.PredicateNode) if "DemandGoal" in x.name]
#
#    for atom in target_PredicateNodes:
#        args = new_var()
#        target = tree('EvaluationLink', atom, args)
#
#        time1 = new_var()
#        time2 = new_var()
#        
#        template1 = tree('AtTimeLink', time1, target)
#        template2 = tree('AtTimeLink', time2, target)
#        seq = tree('SequentialAndLink', time1, time2)
#        
#        conj = (template1, template2, seq)
#        
#        conj = (template1, seq, template2)
#        matches = find_conj(conj, atomspace.get_atoms_by_type(t.Link))
#
#
#        if not len(matches):
#            print '[no changes for %s]' % (atom)
#        
#        for match in matches:
#            #print pp(match.atoms)
#            
#            tv1 = match.atoms[0].tv.mean
#            tv2 = match.atoms[2].tv.mean
#            
#            print target, tv2-tv1
#            
#            if tv2 - tv1 > tv_delta:
#                # increased
#                pred = 'increased'
#            elif tv1 - tv2 > tv_delta:
#                # decreased
#                pred = 'decreased'
#            else:
#                continue
#
#            time2_result = match.subst[time2]
#            args_result = match.subst[args]
#
#            tv = TruthValue(1, 1e35)
#            res = tree('AtTimeLink',
#                     time2_result, 
#                     tree('EvaluationLink',
#                                atomspace.add(t.PredicateNode, name=pred),
#                                tree('ListLink',
#                                    tree('EvaluationLink', 
#                                         atom,
#                                         args_result
#                                    )
#                                )
#                        )
#                    )
#            a = atom_from_tree(res, atomspace)
#            a.tv = tv
#            
#            print str(a)

def notice_changes(atomspace):    
    tv_delta = 0.01    
    
    t = types
    
    times = atomspace.get_atoms_by_type(t.TimeNode)
    times = [f for f in times if f.name != "0"] # Related to a bug in the Psi Modulator system
    times = sorted(times, key= lambda t: int(t.name) )

    target_PredicateNodes = [x for x in atomspace.get_atoms_by_type(t.PredicateNode) if "DemandGoal" in x.name]

    for atom in target_PredicateNodes:
        target = tree('EvaluationLink', atom, tree('ListLink'))

        time = new_var()
        
        # find all of the xDemandGoal AtTimeLinks in order, sort them, then check whether each one is higher/lower than the previous one.       
        
        atTimes = []
        times_with_update = []
        for time in times:
#            # Need to use unify because not sure what the arguments will be. But they must be the same...
#            template = tree('AtTimeLink', time, target)
#            matches = find_conj( (template,) )
#            
#            # If this DemandGoal is in use there will be one value at each timestamp (otherwise none)
#            assert len(matches) < 2
#            matches[0].
            template = tree('AtTimeLink', time, target)
            a = atom_from_tree(template, atomspace)
            
            # Was the value updated at that timestamp? The PsiDemandUpdaterAgent is not run every cycle so many
            # timestamps will have no value recorded.
            if a.tv.count > 0:
                atTimes.append(a)
                times_with_update.append(time)
    
        if len(atTimes) < 2:
            continue
        
        for i, atTime in enumerate(atTimes[:-1]):
            atTime_next = atTimes[i+1]
            
            tv1 = atTime.tv.mean
            tv2 = atTime_next.tv.mean
            
            print tv2-tv1
            
            if tv2 - tv1 > tv_delta:
                # increased
                pred = 'increased'
            elif tv1 - tv2 > tv_delta:
                # decreased
                pred = 'decreased'
            else:
                continue

            time2 = times_with_update[i+1]

            tv = TruthValue(1, 1.0e35)
            res = tree('AtTimeLink',
                     time2,
                     tree('EvaluationLink',
                                atomspace.add(t.PredicateNode, name=pred),
                                tree('ListLink',
                                    target
                                )
                        )
                    )
            a = atom_from_tree(res, atomspace)
            a.tv = tv
            
            print str(a)

#def make_seq_alt(atomspace):
#    # unit of timestamps is 0.1 second so multiply by 10
#    interval = 10* 60
#    times = atomspace.get_atoms_by_type(t.TimeNode)
#    times = [f for f in times if f.name != "0"] # Related to a bug in the Psi Modulator system
#    times = sorted(times, key= lambda t: int(t.name) )
#
#    for (i, time_atom) in enumerate(times[:-1]):
#        t1 = int(time_atom.name)
#        for time2_atom in times[i+1:]:
#            t2 = int(time2_atom.name)
#            if t2 - t1 <= interval:
#                atomspace.add_link(t.SequentialAndLink,  [time_atom,  time2_atom], TruthValue(1, 1))
##                for atTime in time_atom.incoming:
##                    for atTime2 in time2_atom.incoming:
##                        print atomspace.add_link(t.SequentialAndLink,  [atTime,  atTime2], TruthValue(1, 1))
##                        #event1, event2 = atTime.out[1], atTime2.out[1]
##                        #print atomspace.add_link(t.SequentialAndLink,  [event1, event2], TruthValue(1, 1))
#            else:
#                break
#
##    for i in xrange(len(times)-1):
##        (time1,  time2) = (times[i],  times[i+1])
##        # TODO SeqAndLink was not supposed to be used on TimeNodes directly.
##        # But that's more useful for fishgram
##        print atomspace.add_link(t.SequentialAndLink,  [time1,  time2])

class ClockMindAgent(opencog.cogserver.MindAgent):
    def __init__(self):
        self.cycles = 1

    def run(self,atomspace):
        times = atomspace.get_atoms_by_type(t.TimeNode)
        times = sorted(times, key= lambda t: int(t.name) )
        
        print times[-1].name

class FishgramMindAgent(opencog.cogserver.MindAgent):
    def __init__(self):
        self.cycles = 1

    def run(self,atomspace):
        fish = Fishgram(atomspace)
        #make_seq(atomspace)
        # Using the magic evaluator now. But add a dummy link so that the extractForest will include this
        #atomspace.add(t.SequentialAndLink, out=[atomspace.add(t.TimeNode, '0'), atomspace.add(t.TimeNode, '1')], tv=TruthValue(1, 1))
        
        notice_changes(atomspace)
        
        fish.forest.extractForest()
#            
#            conj = (fish.forest.all_trees[0],)
#            fish.forest.lookup_embeddings(conj)

        #fish.forest.extractForest()
        #time1, time2, time1_binding, time2_binding = new_var(), new_var(), new_var(), new_var()
        #fish.forest.tree_embeddings[tree('SequentialAndLink', time1, time2)] = [
        #                                                    {time1: time1_binding, time2: time2_binding}]
#            for layer in fish.closed_bfs_layers():
#                for conj, embs in layer:
#                    print
#                    print pp(conj)
#                    #print pp(embs)
#                    lookup = pp( fish.forest.lookup_embeddings(conj) )
#                    for bt in lookup:
#                        print 'lookup:',  pp(bt)
#                    for binding in embs:
#                        bound_tree = bind_conj(conj, binding)
#                        print 'emb:',  pp(bound_tree)
        
        #fish.iterated_implications()
        fish.implications()
        
        #fish.make_all_psi_rules()

        self.cycles+=1
