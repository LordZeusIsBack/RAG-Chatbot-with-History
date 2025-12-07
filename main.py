from os import getenv

import streamlit as st
from dotenv import load_dotenv
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains.history_aware_retriever import create_history_aware_retriever
from langchain_classic.chains.retrieval import create_retrieval_chain
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

HUGGINGFACE_API_KEY = getenv('HUGGINGFACE_API_KEY')
GROQ_API_KEY = getenv('GROQ_API_KEY')

embeddings = HuggingFaceEmbeddings(model=r'C:\Users\ASUS\.hf_models\all-MiniLM-L6-v2')

st.title('QnA RAG Bot with Chat History')
st.write('Upload PDFs and chat with their content')

api_key = st.text_input('Enter your Groq API Key', type='password')

if api_key:
    llm = ChatGroq(model='llama-3.1-8b-instant', api_key=api_key)
    session_id = st.text_input('Enter your Groq Session ID', value='default')

    if 'store' not in st.session_state:
        st.session_state.store = {}

    uploaded_files = st.file_uploader('Choose PDF file', type='pdf', accept_multiple_files=True)
    if uploaded_files:
        documents = []
        for uploaded_file in uploaded_files:
            temp_pdf = f'./temp.pdf'
            with open(temp_pdf, 'wb') as fp:
                fp.write(uploaded_file.getvalue())
                fp_name = uploaded_file.name

            loader = PyPDFLoader(temp_pdf)
            docs = loader.load()
            documents.extend(docs)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(documents)
        vector_db = Chroma.from_documents(splits, embeddings)
        retriever = vector_db.as_retriever()

        contextualize_q_system_prompt = (
            """Given a chat history and the latest user question
            which might reference context in the chat history,
            formulate a standalone question which can be understood
            without the chat history. DO NOT ANSWER THE QUESTION.
            Just formulate it if needed and otherwise return it as is."""
        )

        contextualize_q_prompt = ChatPromptTemplate.from_messages(
            [
                ('system', contextualize_q_system_prompt),
                MessagesPlaceholder('history_of_chat'),
                ('human', '{input}')
            ]
        )

        history_aware_retriever = create_history_aware_retriever(llm, retriever, contextualize_q_prompt)

        system_prompt = (
            """You're an assistant for question-answering tasks.
            Use the following pieces of retrieved context to answer the question.
            If you don't know the answer, just say that you don't know.
            Use a maximum of three sentences to answer.
            
            Context:
            {context}"""
        )

        qa_prompt = ChatPromptTemplate.from_messages(
            [
                ('system', system_prompt),
                MessagesPlaceholder('history_of_chat'),
                ('human', '{input}')
            ]
        )

        question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
        rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

        def get_session_history(session: str) -> BaseChatMessageHistory:
            if session_id not in st.session_state.store:
                st.session_state.store[session_id] = ChatMessageHistory()
            return st.session_state.store[session_id]

        conversational_rag_chain = RunnableWithMessageHistory(
            rag_chain,
            get_session_history,
            input_messages_key='input',
            history_messages_key='history_of_chat',
            output_messages_key='answer'
        )

        user_input = st.text_input('Your question:')
        if user_input:
            session_history = get_session_history(session_id)
            response = conversational_rag_chain.invoke(
                {'input': user_input},
                config={
                    'configurable': {'session_id': session_id}
                }
            )

            st.write(st.session_state.store)
            st.write('Assistant: ', response['answer'])
            st.write('Chat History: ', session_history.messages)

else:
    st.warning('Enter your API Key.')
