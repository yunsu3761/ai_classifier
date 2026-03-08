from collections import deque
from enrichment import enrich_node_prompt
from classification import classify_prompt, init_classify_prompt, main_classify_prompt
from model_definitions import promptLLM, constructPrompt
from prompts import EnrichSchema
import json
from utils import clean_json_string
from unidecode import unidecode

from classification import ClassifySchema


class Node:
    def __init__(self, id, label, dimension, description=None, children=None, parents=None, source=None):
        """
        Initialize a Node based on the provided JSON schema.

        Args:
        label (str): The label for the node.
        description (str): Description of the node.
        dimension (str): Type of node. Examples are: task, dataset, methodology, evaluation method, application
        children (dict, optional): A dictionary of children nodes, where keys are labels and values are Node instances.
        parents (list of Node, optional): A list of parent nodes of the current node.
        """
        self.id = id
        self.label = label
        self.description = description
        self.dimension = dimension
        self.children = children if children else {}
        self.parents = parents if parents else []
        self.level = 0 if not self.parents else max(parent.level for parent in self.parents) + 1

        self.papers = {}
        self.source = source

    def add_child(self, label, child_node):
        """
        Add a child node to the current node.

        Args:
        label (str): The label for the child node.
        child_node (Node): The child Node to be added.
        """
        if child_node in self.parents:
            print("CANNOT ADD! THIS WOULD ADD A CYCLE!")
        else:
            child_node.add_parent(self)
            child_node.level = min(parent.level for parent in child_node.parents) + 1
            self.children[label] = child_node

    def add_parent(self, parent_node):
        """
        Add a parent node to the current node.

        Args:
        parent_node (Node): The parent Node to be added.
        """
        if parent_node not in self.parents:
            self.parents.append(parent_node)
            self.level = min(parent.level for parent in self.parents) + 1

    def get_parents(self):
        """
        Get the parent nodes of the current node.

        Returns:
        list: A list of parent nodes.
        """
        return self.parents
    
    def get_ancestors(self):
        """
        Get all ancestor nodes of the current node.

        Returns:
        list: A list of ancestor nodes from the root to the current node.
        """
        ancestors = []
        nodes_to_visit = list(self.parents)
        while nodes_to_visit:
            current = nodes_to_visit.pop()
            if current not in ancestors:
                ancestors.append(current)
                nodes_to_visit.extend(current.parents)
        return ancestors
    
    def get_siblings(self):
        """
        Get the siblings of the current node (nodes that share at least one parent).

        Returns:
        set: A set of sibling nodes.
        """
        siblings = set()
        for parent in self.parents:
            for sibling in parent.get_children().values():
                if sibling is not self:
                    siblings.add(sibling)
        return siblings

    def get_children(self):
        """
        Get the children nodes of the current node.

        Returns:
        dict: A dictionary of children nodes where keys are labels and values are Node instances.
        """
        return self.children
    
    def get_phrases(self):
        """
        Get all phrases of the current node and its descendant nodes.

        Returns:
        list: A list of unique phrases from the current node and all of its descendants.
        """
        unique_phrases = set(self.phrases)
        nodes_to_visit = list(self.children.values())
        
        while nodes_to_visit:
            current_node = nodes_to_visit.pop()
            unique_phrases.update(current_node.phrases)
            nodes_to_visit.extend(current_node.children.values())
        
        return list(unique_phrases)

    def get_sentences(self):
        """
        Get all sentences of the current node and its descendant nodes.

        Returns:
        list: A list of unique sentences from the current node and all of its descendants.
        """
        unique_sentences = set(self.sentences)
        nodes_to_visit = list(self.children.values())
        
        while nodes_to_visit:
            current_node = nodes_to_visit.pop()
            unique_sentences.update(current_node.sentences)
            nodes_to_visit.extend(current_node.children.values())
        
        return list(unique_sentences)
    
    def classify_node(self, args, label2node, visited):

        for child_label, child in self.get_children().items():
            if child.id not in visited:
                child.papers = {}

        # Which papers are classified to the current node?
        prompts = []
        for paper_id, paper in self.papers.items():
            prompts.append(constructPrompt(args, init_classify_prompt, main_classify_prompt(self, paper)))

        output = promptLLM(args, prompts, schema=ClassifySchema, max_new_tokens=3000)
        output_dict = [json.loads(clean_json_string(c)) if "```" in c else json.loads(c.strip()) for c in output]
        class_options = [c for c in self.get_children()]
        class_map = {c:0 for c in self.get_children()}
        class_map['unlabeled'] = 0

        for (paper_id, paper), out_labels in zip(self.papers.items(), output_dict):
            if (len(out_labels['class_labels']) == 0) or ("None" in out_labels['class_labels']):
                class_map['unlabeled'] += 1
                continue
            for label in out_labels['class_labels']:
                full_label = label + f'_{self.dimension}'
                if "None" in label:
                    class_map['unlabeled'] += 1
                    continue
                elif (full_label in label2node) and (label in class_options):
                    label2node[full_label].papers[paper_id] = paper
                    class_map[label] += 1
                    paper.labels[self.dimension].append(label)
                else:
                    class_map['unlabeled'] += 1
        
        print(f'classification: {str(class_map)}')
        return output_dict
    
    def display(self, level=0, indent_multiplier=2, visited=None):
        """
        Display the node and its children in a structured manner, handling nodes with multiple parents.

        Args:
        level (int): The current level of the node for indentation purposes.
        indent_multiplier (int): The number of spaces used for indentation, multiplied by the level.
        visited (set): A set of visited node IDs to handle cycles in the directed acyclic graph.
        """
        indent = " " * (level * indent_multiplier)
        
        if visited is None:
            visited = set()
        if self.id in visited:
            print(f"{indent}Label (Visited): {self.label}")
            return
        
        output_dict = {"label": self.label,
                       "description": self.description,
                       "level":self.level,
                       "source":"initial" if self.source is None else self.source
                       }
        
        visited.add(self.id)

        # Safe print function to handle Unicode issues
        def safe_print(text):
            try:
                print(text)
            except UnicodeEncodeError:
                from unidecode import unidecode
                print(unidecode(str(text)))

        safe_print(f"{indent}Label: {self.label}")
        safe_print(f"{indent}Dimension: {self.dimension}")
        safe_print(f"{indent}Description: {self.description}")
        safe_print(f"{indent}Level: {self.level}")
        safe_print(f"{indent}Source: {'Initial' if self.source is None else self.source}")

        if len(self.papers) > 0:
            example_papers = [(p.id, unidecode(p.title)) for p in self.papers.values()]
            output_dict['example_papers'] = example_papers[:10]
            output_dict['paper_ids'] = list(self.papers.keys())

            safe_print(f"{indent}# of Papers: {len(self.papers)}")
            safe_print(f"{indent}Example Papers: {str(example_papers[:3])}")
        if self.children:
            safe_print(f"{indent}{'-'*40}")
            safe_print(f"{indent}Children:")
            output_dict['children'] = []

            for child in self.children.values():
                sub_dict = child.display(level + 1, indent_multiplier, visited)
                if sub_dict is not None:
                    output_dict['children'].append(sub_dict)
            
        safe_print(f"{indent}{'-'*40}")
        return output_dict

    def __repr__(self):
        return f"Node(label={self.label}, dim={self.dimension}, description={self.description}, level={self.level})"
    
    def to_dict(self):
        """
        Serialize the node and its children to a dictionary.
        Iterative implementation to avoid recursion depth limit errors on deep taxonomies.
        """
        # BFS to collect all nodes in level order
        bfs_order = []
        bfs_queue = deque([self])
        seen = set()
        while bfs_queue:
            node = bfs_queue.popleft()
            if node.id in seen:
                continue
            seen.add(node.id)
            bfs_order.append(node)
            for child_node in node.children.values():
                bfs_queue.append(child_node)

        # Build dicts bottom-up (leaves first = reversed BFS order)
        node_dicts = {}
        for node in reversed(bfs_order):
            node_dicts[node.id] = {
                'id': node.id,
                'label': node.label,
                'dimension': node.dimension,
                'description': node.description,
                'level': node.level,
                'source': node.source,
                'children': {
                    child_label: node_dicts[child_node.id]
                    for child_label, child_node in node.children.items()
                    if child_node.id in node_dicts
                }
            }
        return node_dicts[self.id]
    
    @classmethod
    def from_dict(cls, data, id2node, label2node, parent=None):
        """
        Deserialize a node and its children from a dictionary.
        Iterative implementation to avoid recursion depth limit errors on deep taxonomies.
        """
        # Queue items: (data_dict, parent_node, child_label_in_parent)
        queue = deque([(data, parent, None)])
        root_node = None

        while queue:
            current_data, current_parent, label_in_parent = queue.popleft()
            node_id = current_data['id']

            if node_id in id2node:
                node = id2node[node_id]
                # Link to parent if not already linked
                if current_parent:
                    if current_parent not in node.parents:
                        node.parents.append(current_parent)
                        node.level = min(p.level for p in node.parents) + 1
                    current_parent.children[label_in_parent] = node
                if root_node is None:
                    root_node = node
                continue

            node = cls(
                id=node_id,
                label=current_data['label'],
                dimension=current_data['dimension'],
                description=current_data.get('description'),
                source=current_data.get('source')
            )
            id2node[node_id] = node
            label2node[f"{node.label}_{node.dimension}"] = node

            if current_parent:
                node.parents.append(current_parent)
                node.level = current_parent.level + 1
                current_parent.children[label_in_parent] = node

            if root_node is None:
                root_node = node

            for child_label, child_data in current_data.get('children', {}).items():
                queue.append((child_data, node, child_label))

        return root_node
    

class DAG:
    def __init__(self, root, dim):
        """
        Initialize a DAG with a root node.

        Args:
        root (Node): The root node of the DAG.
        """
        self.root = root
        self.dimension = dim

    def enrich_dag(self, args, id2node):
        """
        Iterate through the DAG starting from the root node and call enrich_node on each node.
        """
        visited = set()
        nodes_to_visit = [(self.root, [])]
        prompts = {}
        all_phrases = []
        all_sentences = []

        while nodes_to_visit:
            current_node, ancestors = nodes_to_visit.pop()
            if current_node.id in visited:
                continue
            visited.add(current_node.id)
            # Enrich the current node
            prompts[current_node.id] = enrich_node_prompt(args, current_node, ancestors)
            
            # Add children to visit next with updated ancestors
            new_ancestors = ancestors + [current_node]
            for child in current_node.get_children().values():
                nodes_to_visit.append((child, new_ancestors))

        output = promptLLM(args, list(prompts.values()), schema=EnrichSchema, max_new_tokens=1500)
        output_dict = [json.loads(clean_json_string(c)) if "```" in c else json.loads(c.strip()) for c in output]

        for node_id, out in zip(prompts.keys(), output_dict):
            node = id2node[node_id]

            node.phrases = [p.lower().replace(' ', '_') for p in out['commonsense_key_phrases']]
            all_phrases.extend(node.phrases)

            node.sentences = [p.lower() for p in out['commonsense_sentences']]
            all_sentences.extend(node.sentences)
        
        return all_phrases, all_sentences
    
    def classify_dag(self, args, label2node, start_node=None):
        visited = set()
        # self.root.papers = collection
        if start_node is None:
            nodes_to_visit = [(self.root, self.root.papers)]
        else:
            nodes_to_visit = [(start_node, start_node.papers)]

        while nodes_to_visit:
            current_node, papers = nodes_to_visit.pop()
            if (current_node.id in visited) or len(current_node.get_children()) == 0:
                continue
            for child_label, child in current_node.get_children().items():
                if child.id not in visited:
                    child.papers = {}

            print(f'visiting: {current_node.label}; # of papers: {len(papers)}')

            visited.add(current_node.id)

            # Which papers are classified to the current node?
            prompts = []
            for paper_id, paper in papers.items():
                prompts.append(constructPrompt(args, init_classify_prompt, main_classify_prompt(current_node, paper)))

            output = promptLLM(args, prompts, schema=ClassifySchema, max_new_tokens=1500)
            output_dict = [json.loads(clean_json_string(c)) if "```" in c else json.loads(c.strip()) for c in output]
            class_options = [c for c in current_node.get_children()]

            for (paper_id, paper), out_labels in zip(papers.items(), output_dict):
                if len(out_labels['class_labels']) == 0:
                    continue
                for label in out_labels['class_labels']:
                    if "None" in label:
                        continue
                    elif (label in label2node) and (label in class_options):
                        label2node[label].papers[paper_id] = paper
                        paper.labels[current_node.dimension].append(label)
            
            # Add children to visit next with updated ancestors
            for child in current_node.get_children().values():
                nodes_to_visit.append((child, child.papers))
        
        return output_dict
