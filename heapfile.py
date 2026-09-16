import struct
import os


class RID:
    def __init__(self, page_id, slot_id):
        self.page_id=page_id
        self.slot_id=slot_id
    
    def __eq__(self, other):
        return self.page_id == other.page_id and self.slot_id == other.slot_id

class Heapfile:
    def __init__(self, filename, page_size, record_format):
        self.FILE_HEADER_FORMAT = "iiii" #tamaño de pagina, total de paginas, total de registros, first page id
        self.PAGE_HEADER_FORMAT = "iiii" #id, numero de registros, numero de registros activos, free list head
        self.filename=filename
        self.PAGE_SIZE=page_size
        self.RECORD_FORMAT=record_format+"i"
        self.RECORD_SIZE = struct.calcsize(record_format)
        self.FILE_HEADER_SIZE=struct.calcsize(self.FILE_HEADER_FORMAT)
        self.PAGE_HEADER_SIZE = struct.calcsize(self.PAGE_HEADER_FORMAT)
        self.SLOT_PER_PAGE=(page_size-self.PAGE_HEADER_SIZE)//self.RECORD_SIZE
        if self.SLOT_PER_PAGE <= 0:
            raise ValueError("page_size es demasiado pequeño para el header y el registro")
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            with open(filename, "wb") as f:
                f.write(struct.pack(self.FILE_HEADER_FORMAT, self.PAGE_SIZE,0,0,1))
                f.write(b"\x00" * (self.PAGE_SIZE - self.FILE_HEADER_SIZE))

    def calcular_slot(self, page_id, slot_id):
        return (self.PAGE_SIZE*page_id)+self.PAGE_HEADER_SIZE+(slot_id*se   lf.RECORD_SIZE)
    
    def read_file_header(self):
        with open(self.filename,"rb") as f:
            f.seek(0)
            data=f.read(self.FILE_HEADER_SIZE)            
            page_size, tot_pag, tot_reg, first_id=struct.unpack(self.FILE_HEADER_FORMAT, data)
            return page_size, tot_pag, tot_reg, first_id
        
    def read_page_header(self,page_id):
        with open(self.filename, "rb") as f:
            f.seek(self.PAGE_SIZE*page_id)
            data=f.read(self.PAGE_HEADER_SIZE)
            id, num_reg, reg_act, free_list=struct.unpack(self.PAGE_HEADER_FORMAT, data)
            return id, num_reg, reg_act, free_list
        
    def new_page(self):
        with open(self.filename, "r+b") as f:
            page_size, tot_pag, tot_reg, first_id=self.read_file_header()
            new_page_id=tot_pag+1

            page_offset=new_page_id*self.PAGE_SIZE
            f.seek(page_offset)

            page_header=struct.pack(self.PAGE_HEADER_FORMAT, new_page_id, 0, 0, -1)
            f.write(page_header)
            f.write(b"\x00" * (self.PAGE_SIZE - self.PAGE_HEADER_SIZE))

            tot_pag=tot_pag+1
            f.seek(0)
            f.write(struct.pack(self.FILE_HEADER_FORMAT, page_size, tot_pag, tot_reg, first_id))

        return new_page_id

    def actualizar_file_header(self, añadir_pagina, añadir_registro):
        with open(self.filename, "r+b") as f:
            page_size, num_paginas, num_records, first_id=self.read_file_header()
            if(añadir_pagina):
                num_paginas+=1
            if(añadir_registro):
                num_records+=1
            f.seek(0)
            f.write(struct.pack(self.FILE_HEADER_FORMAT,self.PAGE_SIZE, num_paginas, num_records, 1))

    def actualizar_page_header(self, page_id ,nuevo_registro, eliminar_registro, nuevo_free_list_head=-1):
        with open(self.filename, "r+b") as f:
            id, num_registros, num_activos, free_list=self.read_page_header(page_id)
            if nuevo_registro:
                num_registros+=1
                num_activos+=1
            if eliminar_registro:
                num_activos-=1
            if(nuevo_free_list_head!=-1):
                free_list=nuevo_free_list_head
            f.seek(page_id*self.PAGE_SIZE)
            f.write(struct.pack(self.PAGE_HEADER_FORMAT, id, num_registros, num_activos, free_list))
            
        
    def insert_sin_espacio(self, *registro):
        with open(self.filename, "r+b") as f:
            page_size, tot_pag, tot_reg, first_id=self.read_file_header()
            for page_id in range(1,tot_pag+1):
                id, num_reg, reg_act, free_list=self.read_page_header(page_id)
                if num_reg<self.SLOT_PER_PAGE:
                    f.seek(self.calcular_slot(page_id,num_reg))
                    f.write(struct.pack(self.RECORD_FORMAT, *registro))
                    self.actualizar_file_header(False, True)
                    self.actualizar_page_header(page_id,True,False)
                    return RID(page_id,num_reg)
            new_page_id=self.new_page()
            f.seek(self.calcular_slot(new_page_id,0))
            f.write(struct.pack(self.RECORD_FORMAT, *registro))
            self.actualizar_file_header(False,True)
            self.actualizar_page_header(new_page_id, True,False)
            return RID(new_page_id,0)

    def insert(self, *registro):
        with open(self.filename, "r+b") as f:
            page_size, tot_pag, tot_reg, first_id = self.read_file_header()
            for page_id in range(1, tot_pag + 1):
                page_id_leido, num_reg, reg_act, free_list = self.read_page_header(page_id)
                if free_list != -1:
                    slot_id = free_list
                    slot_offset = self.calcular_slot(page_id, slot_id)
                    f.seek(slot_offset + self.RECORD_SIZE) 
                    next_free = struct.unpack("i", f.read(4))[0]
                    f.seek(slot_offset)
                    f.write(struct.pack(self.RECORD_FORMAT, *registro,-1))
                    self.actualizar_page_header(page_id, nuevo_registro=True, eliminar_registro=False, nuevo_free_list_head=next_free)
                    self.actualizar_file_header(False, True)
                    return RID(page_id, slot_id)
            new_page_id = self.new_page()
            slot_id = 0
            slot_offset = self.calcular_slot(new_page_id, slot_id)
            f.seek(slot_offset)
            f.write(struct.pack(self.RECORD_FORMAT, *registro, -1))
            self.actualizar_file_header(False, True)
            self.actualizar_page_header(new_page_id, nuevo_registro=True, eliminar_registro=False)
            return RID(new_page_id, slot_id)





